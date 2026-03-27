"""Supabase dedup + logging.

Tables expected:
  - replied_tweets(tweet_id text PK, author_username text, reply_text text,
                   tweet_url text, keyword text, score float, posted_at timestamptz,
                   reply_tweet_id text, engagement_likes int, engagement_impressions int,
                   engagement_checked timestamptz, reply_style text, source_type text,
                   post_type text)
  - keyword_stats(keyword text PK, attempts int, successes int, total_likes int,
                  total_impressions int, last_used timestamptz, last_success timestamptz)
  - reply_reviews(... raw_input text)
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz
from supabase import create_client, Client

from tweetgod.config import settings
from tweetgod.models import PostedQuote, KeywordStats, Tweet

log = logging.getLogger(__name__)

_client: Client | None = None

# In-memory set of tweet IDs we've already sent watchlist alerts for.
# Resets on restart, which is fine — the scraper only looks back 2 hours.
_watchlist_alerted: set[str] = set()


def is_watchlist_alerted(tweet_id: str) -> bool:
    """Check if we've already sent a watchlist alert for this tweet."""
    return tweet_id in _watchlist_alerted


def mark_watchlist_alerted(tweet_id: str) -> None:
    """Record that we've sent a watchlist alert for this tweet."""
    _watchlist_alerted.add(tweet_id)


def _today_start_utc() -> str:
    """Get the start of 'today' in the configured timezone, as a UTC ISO string."""
    tz = pytz.timezone(settings.timezone)
    now_local = datetime.now(tz)
    local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(pytz.utc)
    return utc_midnight.strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


# ── Dedup ────────────────────────────────────────────────────────────────────


def get_replied_tweet_ids(tweet_ids: list[str]) -> set[str]:
    """Check which tweet_ids we've already replied to or reviewed.

    Checks both replied_tweets (posted) and reply_reviews (seen/skipped)
    so we never show the same tweet twice.
    """
    if not tweet_ids:
        return set()

    client = _get_client()
    # Check posted replies
    resp = (
        client.table("replied_tweets")
        .select("tweet_id")
        .in_("tweet_id", tweet_ids)
        .execute()
    )
    seen = {row["tweet_id"] for row in resp.data}

    # Also check reviewed tweets (approved, rejected, edited — all seen)
    resp2 = (
        client.table("reply_reviews")
        .select("tweet_id")
        .in_("tweet_id", tweet_ids)
        .execute()
    )
    seen.update(row["tweet_id"] for row in resp2.data)

    return seen


def get_today_post_count() -> int:
    """How many posts we've made today (in configured timezone)."""
    client = _get_client()
    resp = (
        client.table("replied_tweets")
        .select("tweet_id", count="exact")
        .gte("posted_at", _today_start_utc())
        .execute()
    )
    return resp.count or 0


# ── Diversity queries ────────────────────────────────────────────────────────


def get_today_author_reply_count(username: str) -> int:
    """How many times we've quoted this author today (in configured timezone)."""
    client = _get_client()
    resp = (
        client.table("replied_tweets")
        .select("tweet_id", count="exact")
        .eq("author_username", username)
        .gte("posted_at", _today_start_utc())
        .execute()
    )
    return resp.count or 0


def get_today_replied_authors() -> set[str]:
    """Get set of author usernames we've already quoted today (in configured timezone)."""
    client = _get_client()
    resp = (
        client.table("replied_tweets")
        .select("author_username")
        .gte("posted_at", _today_start_utc())
        .execute()
    )
    return {row["author_username"] for row in resp.data}


# ── Save quote ───────────────────────────────────────────────────────────────


def save_quote(quote: PostedQuote) -> None:
    """Insert a posted quote tweet into Supabase."""
    client = _get_client()
    client.table("replied_tweets").insert(
        {
            "tweet_id": quote.tweet_id,
            "reply_tweet_id": quote.quote_tweet_id,
            "author_username": quote.author_username,
            "reply_text": quote.quote_text,
            "tweet_url": quote.tweet_url,
            "keyword": quote.keyword_used,
            "score": quote.score,
            "posted_at": quote.posted_at.isoformat(),
            "source_type": quote.source_type,
            "post_type": "quote_tweet",
        }
    ).execute()
    log.info("Saved quote tweet for tweet %s (source=%s)", quote.tweet_id, quote.source_type)


# ── Review logging ───────────────────────────────────────────────────────────


def save_review(
    tweet: Tweet,
    ai_reply_text: str,
    final_reply_text: str,
    outcome: str,
    source_type: str,
    score: float,
    keyword: str,
    response_time_seconds: int | None,
    raw_input: str = "",
) -> None:
    """Insert a review decision into the reply_reviews table."""
    client = _get_client()
    client.table("reply_reviews").insert(
        {
            "tweet_id": tweet.tweet_id,
            "author_username": tweet.author_username,
            "tweet_text": tweet.text,
            "tweet_url": tweet.url,
            "ai_reply_text": ai_reply_text,
            "final_reply_text": final_reply_text,
            "outcome": outcome,
            "source_type": source_type,
            "score": score,
            "keyword": keyword,
            "response_time_seconds": response_time_seconds,
            "raw_input": raw_input,
        }
    ).execute()
    log.info("Saved review for tweet %s (outcome=%s)", tweet.tweet_id, outcome)


# ── Keyword stats ────────────────────────────────────────────────────────────


def get_keyword_stats(keyword: str) -> KeywordStats | None:
    """Fetch stats for a single keyword."""
    client = _get_client()
    resp = (
        client.table("keyword_stats")
        .select("*")
        .eq("keyword", keyword)
        .execute()
    )
    if not resp.data:
        return None
    row = resp.data[0]
    return KeywordStats(**row)


def get_all_keyword_stats() -> dict[str, KeywordStats]:
    """Fetch stats for all keywords."""
    client = _get_client()
    resp = client.table("keyword_stats").select("*").execute()
    return {row["keyword"]: KeywordStats(**row) for row in resp.data}


def upsert_keyword_stats(stats: KeywordStats) -> None:
    """Insert or update keyword stats."""
    client = _get_client()
    client.table("keyword_stats").upsert(
        {
            "keyword": stats.keyword,
            "attempts": stats.attempts,
            "successes": stats.successes,
            "total_likes": stats.total_likes,
            "total_impressions": stats.total_impressions,
            "last_used": stats.last_used.isoformat() if stats.last_used else None,
            "last_success": stats.last_success.isoformat() if stats.last_success else None,
        }
    ).execute()


def increment_keyword_attempt(keyword: str) -> None:
    """Record that we used this keyword (regardless of outcome)."""
    stats = get_keyword_stats(keyword) or KeywordStats(keyword=keyword)
    stats.attempts += 1
    stats.last_used = datetime.utcnow()
    upsert_keyword_stats(stats)
