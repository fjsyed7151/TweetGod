"""TweetGod — main entry point and scheduler."""

from __future__ import annotations

import asyncio
import logging
import math
import random
import sys
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import tweetgod.approval as approval_mod
from tweetgod.approval import request_approval, _get_updates
from tweetgod.config import settings, TRENDING_KEYWORDS, WATCHLIST_KEYWORDS
from tweetgod.dedup import (
    get_replied_tweet_ids,
    get_today_post_count,
    get_today_replied_authors,
    increment_keyword_attempt,
    is_watchlist_alerted,
    mark_watchlist_alerted,
    save_quote,
    save_review,
    get_all_keyword_stats,
)
from tweetgod.engagement_tracker import check_reply_engagement
from tweetgod.filters import filter_tweets, apply_diversity_filter
from tweetgod.models import PostedQuote
from tweetgod.notifier import (
    notify_daily_limit,
    notify_failure,
    notify_no_tweets,
    notify_paused,
    notify_resumed,
    notify_status,
    notify_success,
    notify_watchlist_tweet,
    send_message,
)
from tweetgod.pause import (
    is_paused,
    parse_pause_command,
    pause_for,
    pause_until_tomorrow,
    resume,
    get_paused_until,
    format_remaining,
)
from tweetgod.poster import post_quote_tweet
from tweetgod.scorer import rank_tweets
from tweetgod.scraper import scrape_tweets, scrape_watchlist
from tweetgod.selector import select_keyword

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("tweetgod")


# ── Softmax selection ────────────────────────────────────────────────────────


def _softmax_pick(ranked, temperature: float = 0.5):
    """Pick a candidate from ranked list using softmax with temperature."""
    if len(ranked) <= 1:
        return ranked[0]

    scores = [s.score for s in ranked]
    max_score = max(scores)
    exps = [math.exp((s - max_score) / temperature) for s in scores]
    total = sum(exps)
    probs = [e / total for e in exps]

    chosen = random.choices(ranked, weights=probs, k=1)[0]
    log.info(
        "Softmax pick: selected @%s (score=%.2f) from %d candidates",
        chosen.tweet.author_username, chosen.score, len(ranked),
    )
    return chosen


# ── Scraping helpers ─────────────────────────────────────────────────────────


async def _scrape_with_retries(keyword: str, search_type: str, max_retries: int = 3) -> list:
    """Scrape tweets with retries. Returns empty list on total failure."""
    for attempt in range(max_retries):
        tweets = await scrape_tweets(keyword, search_type)
        if tweets:
            return tweets
        if attempt < max_retries - 1:
            wait = 30 * (2 ** attempt)
            log.warning("No tweets returned, retry %d/%d in %ds", attempt + 1, max_retries, wait)
            await asyncio.sleep(wait)
    log.warning("All %d scrape attempts failed for %s/%s", max_retries, search_type, keyword)
    return []


# ── Pipeline ─────────────────────────────────────────────────────────────────


async def run_pipeline(dry_run: bool = False) -> PostedQuote | None:
    """Execute the full quote tweet pipeline once.

    1. Check rate limits & active hours
    2. Select keyword/priority/community
    3. Scrape tweets
    4. Filter + dedup + author diversity filter
    5. Score + rank
    6. Softmax pick from top-N
    7. Present to user via Telegram, get their take, polish, iterate
    8. Post quote tweet + save + notify

    Returns the PostedQuote if successful, None otherwise.
    """
    # ── Step 1: Rate limits ──
    if is_paused():
        log.info("Bot is paused (%s), skipping", format_remaining())
        return None

    if not _is_active_hours():
        log.info("Outside active hours, skipping")
        return None

    posts_today = get_today_post_count()
    if posts_today >= settings.daily_post_limit:
        log.info("Daily limit reached (%d/%d)", posts_today, settings.daily_post_limit)
        await notify_daily_limit()
        return None

    # ── Step 2: Select keyword ──
    all_stats = get_all_keyword_stats()
    keyword, search_type = select_keyword(all_stats)
    increment_keyword_attempt(keyword)
    log.info("Pipeline run: keyword='%s' type=%s", keyword, search_type)

    # ── Step 3: Scrape ──
    retries = 1 if search_type in ("community", "priority") else settings.max_retries
    tweets = await _scrape_with_retries(keyword, search_type, max_retries=retries)
    log.info("Scraped %d tweets", len(tweets))

    # ── Step 4: Filter + dedup + author diversity filter + dynamic fallback ──
    if tweets:
        tweet_ids = [t.tweet_id for t in tweets]
        already_replied = get_replied_tweet_ids(tweet_ids)
        replied_authors = get_today_replied_authors()
        filtered = filter_tweets(tweets, already_replied, search_type)
        filtered = apply_diversity_filter(filtered, replied_authors)
    else:
        filtered = []
        replied_authors = get_today_replied_authors()

    # Dynamic fallback: community → priority → trending → keyword
    if not filtered and search_type == "community":
        log.info("Community mode yielded 0 candidates, falling back to priority")
        search_type = "priority"
        tweets = await scrape_tweets("priority", search_type)
        if tweets:
            tweet_ids = [t.tweet_id for t in tweets]
            already_replied = get_replied_tweet_ids(tweet_ids)
            filtered = filter_tweets(tweets, already_replied, search_type)
            filtered = apply_diversity_filter(filtered, replied_authors)

    if not filtered and search_type == "priority":
        log.info("Priority mode yielded 0 candidates, falling back to trending")
        keyword = random.choice(TRENDING_KEYWORDS)
        search_type = "trending"
        tweets = await scrape_tweets(keyword, search_type)
        if tweets:
            tweet_ids = [t.tweet_id for t in tweets]
            already_replied = get_replied_tweet_ids(tweet_ids)
            filtered = filter_tweets(tweets, already_replied, search_type)
            filtered = apply_diversity_filter(filtered, replied_authors)

    if not filtered and search_type == "trending":
        log.info("Trending mode yielded 0 candidates, falling back to keyword")
        keyword, search_type = select_keyword(all_stats)
        if search_type != "keyword":
            search_type = "keyword"
        tweets = await scrape_tweets(keyword, search_type)
        if tweets:
            tweet_ids = [t.tweet_id for t in tweets]
            already_replied = get_replied_tweet_ids(tweet_ids)
            filtered = filter_tweets(tweets, already_replied, search_type)
            filtered = apply_diversity_filter(filtered, replied_authors)

    if not filtered:
        log.info("No tweets passed quality + diversity filter (after fallbacks)")
        await notify_no_tweets(keyword, search_type)
        return None

    # ── Step 5: Score + rank ──
    ranked = rank_tweets(
        filtered,
        top_n=settings.top_n_candidates,
        source_type=search_type,
    )

    # ── Step 6: Softmax pick ──
    best = _softmax_pick(ranked)
    log.info(
        "Best tweet: @%s (score=%.2f) — %s",
        best.tweet.author_username,
        best.score,
        best.tweet.text[:80],
    )

    # ── Step 7: Approval flow (user writes their take, LLM polishes, iterate) ──
    approval = await request_approval(
        candidate=best,
        keyword=keyword,
        score=best.score,
        search_type=search_type,
    )

    # Log the review
    save_review(
        tweet=best.tweet,
        ai_reply_text="",
        final_reply_text=approval.final_text,
        outcome=approval.outcome,
        source_type=search_type,
        score=best.score,
        keyword=keyword,
        response_time_seconds=approval.response_time_seconds,
        raw_input=approval.raw_input,
    )

    if approval.outcome in ("rejected", "timeout"):
        log.info("Tweet skipped (outcome=%s)", approval.outcome)
        return None

    # ── Step 8: Post quote tweet + save + notify ──
    if dry_run:
        log.info("DRY RUN — would quote tweet: %s", best.tweet.url)
        return None

    posted = post_quote_tweet(approval.final_text, best.tweet.tweet_id)
    if posted is None:
        await notify_failure("Twitter API post failed", keyword)
        return None

    posted.author_username = best.tweet.author_username
    posted.tweet_url = best.tweet.url
    posted.keyword_used = keyword
    posted.score = best.score
    posted.source_type = search_type
    save_quote(posted)
    await notify_success(posted, keyword, best.score)

    log.info("Pipeline complete: quote tweeted @%s (source=%s)",
             posted.author_username, search_type)
    return posted


async def _telegram_command_listener() -> None:
    """Background task that listens for /pause, /resume, /status commands."""
    log.info("Telegram command listener started")
    offset: int | None = None
    chat_id = str(settings.telegram_chat_id)

    # Flush stale updates on startup
    updates = await _get_updates()
    if updates:
        offset = max(u["update_id"] for u in updates) + 1

    while True:
        try:
            # Back off when approval is actively polling (it handles commands itself)
            if approval_mod.approval_active:
                await asyncio.sleep(1)
                continue

            updates = await _get_updates(offset=offset)

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue
                if str(msg.get("chat", {}).get("id")) != chat_id:
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                cmd = parse_pause_command(text)
                if cmd is None:
                    continue

                cmd_name, cmd_kwargs = cmd
                if cmd_name == "pause":
                    until = pause_for(**cmd_kwargs)
                    await notify_paused(until)
                elif cmd_name == "pause_today":
                    until = pause_until_tomorrow()
                    await notify_paused(until)
                elif cmd_name == "resume":
                    resume()
                    await notify_resumed()
                elif cmd_name == "status":
                    await notify_status(get_paused_until(), get_today_post_count())

            await asyncio.sleep(3)
        except Exception:
            log.error("Command listener error", exc_info=True)
            await asyncio.sleep(10)


# ── Watchlist monitor ────────────────────────────────────────────────────────


async def run_watchlist() -> None:
    """Check Claude Code watchlist accounts for new tweets and alert via Telegram.

    Runs alongside the main pipeline. Scrapes watchlist accounts, filters for
    Claude Code keywords, deduplicates, and sends Telegram alerts for new hits.
    Only alerts on tweets < 2 hours old, and collapses threads into one alert.
    """
    try:
        tweets = await scrape_watchlist()
        if not tweets:
            log.debug("Watchlist: no tweets returned")
            return

        keywords_lower = [kw.lower() for kw in WATCHLIST_KEYWORDS]

        # Filter: keyword match, age < 2h, not already alerted
        candidates = []
        for tweet in tweets:
            if is_watchlist_alerted(tweet.tweet_id):
                continue
            if tweet.age_hours > 2.0:
                continue
            text_lower = tweet.text.lower()
            matched = [kw for kw in keywords_lower if kw in text_lower]
            if not matched:
                continue
            candidates.append((tweet, matched))

        # Collapse threads: keep only the first tweet per author per cycle
        seen_authors: set[str] = set()
        alerted = 0

        for tweet, matched in candidates:
            if tweet.author_username in seen_authors:
                mark_watchlist_alerted(tweet.tweet_id)
                continue
            seen_authors.add(tweet.author_username)

            mark_watchlist_alerted(tweet.tweet_id)
            await notify_watchlist_tweet(tweet, matched)
            alerted += 1
            log.info(
                "Watchlist alert: @%s — %s (matched: %s)",
                tweet.author_username,
                tweet.text[:80],
                ", ".join(matched),
            )

        log.info("Watchlist: %d scraped, %d candidates, %d alerts sent",
                 len(tweets), len(candidates), alerted)
    except Exception:
        log.error("Watchlist monitor error", exc_info=True)


def _is_active_hours() -> bool:
    """Check if current time is within active posting hours."""
    tz = pytz.timezone(settings.timezone)
    now = datetime.now(tz)
    return settings.active_hour_start <= now.hour < settings.active_hour_end


# ── Scheduler ────────────────────────────────────────────────────────────────


def start_scheduler() -> None:
    """Start the APScheduler with random jitter."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # Main quote tweet pipeline — runs every 25-55 min (randomized)
    scheduler.add_job(
        _jittered_pipeline,
        IntervalTrigger(minutes=settings.schedule_interval_min),
        id="quote_pipeline",
        name="Quote Tweet Pipeline",
        max_instances=1,
    )

    # Engagement tracker — runs every 6 hours
    scheduler.add_job(
        check_reply_engagement,
        IntervalTrigger(hours=6),
        id="engagement_tracker",
        name="Engagement Tracker",
        max_instances=1,
    )

    scheduler.start()
    log.info(
        "Scheduler started: pipeline every %d-%d min, engagement check every 6h",
        settings.schedule_interval_min,
        settings.schedule_interval_max,
    )


async def _jittered_pipeline() -> None:
    """Add random jitter before running the pipeline."""
    jitter = random.randint(0, (settings.schedule_interval_max - settings.schedule_interval_min) * 60)
    log.info("Jitter: waiting %d seconds before pipeline run", jitter)
    await asyncio.sleep(jitter)
    # Run watchlist monitor alongside the main pipeline
    await asyncio.gather(
        run_watchlist(),
        run_pipeline(),
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    """Boot TweetGod."""
    # Optional Sentry
    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn)

    log.info("TweetGod starting up")
    log.info("Daily limit: %d, Active hours: %d-%d %s",
             settings.daily_post_limit, settings.active_hour_start,
             settings.active_hour_end, settings.timezone)

    async def _run() -> None:
        start_scheduler()
        if settings.telegram_bot_token and settings.telegram_chat_id:
            asyncio.create_task(_telegram_command_listener())
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    # Support: python -m tweetgod.main --dry-run
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        asyncio.run(run_pipeline(dry_run=True))
    else:
        main()
