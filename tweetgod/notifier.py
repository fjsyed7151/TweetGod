"""Telegram notification sender."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
import pytz

from tweetgod.config import settings
from tweetgod.models import PostedQuote

log = logging.getLogger(__name__)


async def send_message(text: str) -> None:
    """Send a message to the configured Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("Telegram not configured, skipping notification")
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception:
        log.error("Telegram notification failed", exc_info=True)


async def notify_success(quote: PostedQuote, keyword: str, score: float) -> None:
    """Send a success notification for a posted quote tweet."""
    source_label = f"\nSource: {quote.source_type}" if quote.source_type != "keyword" else ""
    # Only build an X URL if we have a real X status id (not a "tf:"-prefixed
    # Typefully draft id awaiting resolution by engagement_tracker).
    if quote.quote_tweet_id and not quote.quote_tweet_id.startswith("tf:"):
        link_line = f"\n\U0001f517 https://x.com/i/status/{quote.quote_tweet_id}"
    else:
        link_line = ""
    text = (
        f"<b>Quote tweet posted</b>\n\n"
        f"Quoting: https://x.com/{quote.author_username}\n"
        f"Original: {quote.tweet_url}\n"
        f"Quote: <i>{quote.quote_text}</i>\n"
        f"Keyword: {keyword}\n"
        f"Score: {score:.2f}{source_label}{link_line}"
    )
    await send_message(text)


async def notify_failure(error: str, keyword: str) -> None:
    """Send a failure notification."""
    text = f"<b>Quote tweet failed</b>\n\nKeyword: {keyword}\nError: {error}"
    await send_message(text)


async def notify_no_tweets(keyword: str, search_type: str) -> None:
    """Notify when no quality tweets were found."""
    text = (
        f"<b>No quality tweets found</b>\n\n"
        f"Search: {search_type}\n"
        f"Keyword: {keyword}"
    )
    await send_message(text)


async def notify_daily_limit() -> None:
    """Notify when daily limit is reached."""
    await send_message(f"<b>Daily limit reached</b> ({settings.daily_post_limit} posts)")


async def notify_paused(until: datetime) -> None:
    """Notify that the bot has been paused."""
    time_str = until.strftime("%I:%M %p %Z")
    await send_message(f"\u23f8 <b>Paused</b> until {time_str}")


async def notify_resumed() -> None:
    """Notify that the bot has been resumed."""
    await send_message("\u25b6\ufe0f <b>Resumed!</b> Back to posting.")


async def notify_status(paused_until: datetime | None, posts_today: int) -> None:
    """Send current bot status."""
    from tweetgod.pause import format_remaining
    if paused_until:
        time_str = paused_until.strftime("%I:%M %p %Z")
        pause_line = f"Status: Paused until {time_str} ({format_remaining()})"
    else:
        pause_line = "Status: Active"
    text = (
        f"<b>Bot Status</b>\n\n"
        f"{pause_line}\n"
        f"Posts today: {posts_today}/{settings.daily_post_limit}"
    )
    await send_message(text)


async def notify_watchlist_tweet(tweet, matched_keywords: list[str]) -> None:
    """Send an instant Telegram alert for a Claude Code watchlist tweet."""
    kw_str = ", ".join(matched_keywords) if matched_keywords else "watchlist account"
    age_str = f"{tweet.age_hours:.1f}h ago" if tweet.age_hours < 999 else "recent"
    text = (
        f"<b>Claude Code Alert</b>\n\n"
        f"https://x.com/{tweet.author_username} ({age_str})\n\n"
        f"<i>{tweet.text[:500]}</i>\n\n"
        f"Matched: {kw_str}\n"
        f"\U0001f517 {tweet.url}"
    )
    await send_message(text)


def _fmt_hour_12(hour: int) -> str:
    """Convert a 24-hour int (0-23) to '9 AM' / '9 PM' / '12 AM' / '12 PM' style."""
    if hour == 0:
        return "12 AM"
    if hour == 12:
        return "12 PM"
    if hour < 12:
        return f"{hour} AM"
    return f"{hour - 12} PM"


async def notify_start_of_day() -> None:
    """Telegram heartbeat at the start of the active posting window."""
    from tweetgod.pause import is_paused, format_remaining

    tz_label = datetime.now(pytz.timezone(settings.timezone)).tzname()
    pause_note = ""
    if is_paused():
        pause_note = f" (paused: {format_remaining()})"

    text = (
        f"☀️ <b>Starting daily run{pause_note}</b>\n"
        f"Active until {_fmt_hour_12(settings.active_hour_end)} {tz_label} — "
        f"limit {settings.daily_post_limit} posts"
    )
    await send_message(text)


async def notify_stop_of_day() -> None:
    """Telegram heartbeat at the end of the active posting window."""
    from tweetgod.dedup import get_today_post_count

    tz_label = datetime.now(pytz.timezone(settings.timezone)).tzname()
    posts_today = get_today_post_count()

    text = (
        f"\U0001f319 <b>Stopped for the day</b>\n"
        f"Posts: {posts_today}/{settings.daily_post_limit} — "
        f"resuming at {_fmt_hour_12(settings.active_hour_start)} {tz_label}"
    )
    await send_message(text)


async def notify_daily_summary(posts_today: int, total_score: float) -> None:
    """Send an end-of-day summary."""
    text = (
        f"<b>Daily summary</b>\n\n"
        f"Quote tweets posted: {posts_today}\n"
        f"Total score: {total_score:.2f}\n"
        f"Avg score: {total_score / max(posts_today, 1):.2f}"
    )
    await send_message(text)


async def notify_weekly_digest(days: int = 7) -> None:
    """Build the self-improvement digest and post it to Telegram.

    Telegram's sendMessage max body is 4096 chars; the digest stays well
    under that even with hundreds of reviews thanks to the top-N trims
    inside build_weekly_digest.
    """
    import asyncio
    from tweetgod.digest import build_weekly_digest
    try:
        # Supabase queries are synchronous — push to a worker thread so we
        # don't block the asyncio scheduler loop while assembling the digest.
        text = await asyncio.to_thread(build_weekly_digest, days)
    except Exception:
        log.error("Weekly digest assembly failed", exc_info=True)
        await send_message(
            f"⚠️ <b>Weekly digest failed</b>\n"
            f"Couldn't assemble the {days}d summary. Check Sentry for the trace."
        )
        return

    if not text:
        log.info("Weekly digest empty — nothing to send")
        return

    await send_message(text)
