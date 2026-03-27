"""Engagement tracker — the feedback loop.

Checks quote tweet performance 24h after posting and updates keyword_stats
in Supabase with real engagement data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import tweepy

from tweetgod.config import settings
from tweetgod.dedup import (
    _get_client as get_supabase,
    get_keyword_stats,
    upsert_keyword_stats,
)
from tweetgod.models import KeywordStats

log = logging.getLogger(__name__)


def _get_twitter_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=settings.twitter_bearer_token,
        wait_on_rate_limit=True,
    )


async def check_reply_engagement() -> dict:
    """Check engagement on posts made ~24h ago.

    Fetches posts from Supabase that were posted 20-28h ago,
    looks up their engagement via Twitter API, and updates keyword_stats.
    """
    supabase = get_supabase()
    twitter = _get_twitter_client()

    now = datetime.utcnow()
    window_start = (now - timedelta(hours=28)).isoformat() + "Z"
    window_end = (now - timedelta(hours=20)).isoformat() + "Z"

    # Fetch posts in the 24h window that haven't been checked yet
    resp = (
        supabase.table("replied_tweets")
        .select("*")
        .gte("posted_at", window_start)
        .lte("posted_at", window_end)
        .is_("engagement_checked", "null")
        .execute()
    )

    if not resp.data:
        log.info("No posts to check for engagement")
        return {"checked": 0}

    results = {"checked": 0, "with_engagement": 0, "total_likes": 0}

    for row in resp.data:
        reply_tweet_id = row.get("reply_tweet_id")
        if not reply_tweet_id:
            continue

        try:
            tweet_data = twitter.get_tweet(
                reply_tweet_id,
                tweet_fields=["public_metrics"],
            )
            if tweet_data.data is None:
                continue

            metrics = tweet_data.data.public_metrics or {}
            likes = metrics.get("like_count", 0)
            impressions = metrics.get("impression_count", 0)

            # Fallback: if impressions missing, estimate from likes
            if not impressions and likes > 0:
                impressions = likes * 100

            results["checked"] += 1
            results["total_likes"] += likes

            # Update the post record with engagement data
            supabase.table("replied_tweets").update(
                {
                    "engagement_likes": likes,
                    "engagement_impressions": impressions,
                    "engagement_checked": now.isoformat(),
                }
            ).eq("reply_tweet_id", reply_tweet_id).execute()

            # Update keyword stats if post got meaningful engagement
            keyword = row.get("keyword", "")

            eng_rate = likes / impressions if impressions > 0 else 0.0
            success = eng_rate >= 0.005  # 0.5% like-to-impression ratio

            if success:
                results["with_engagement"] += 1
                if keyword:
                    _update_keyword_success(keyword, likes, impressions)
            else:
                if keyword and likes > 0:
                    _update_keyword_success(keyword, likes, impressions)

        except tweepy.TweepyException:
            log.warning("Failed to fetch engagement for %s", reply_tweet_id, exc_info=True)
            continue

    log.info(
        "Engagement check: %d posts checked, %d with meaningful engagement "
        "(>=0.5%% like/impression rate), %d total likes",
        results["checked"],
        results["with_engagement"],
        results["total_likes"],
    )
    return results


def _update_keyword_success(keyword: str, likes: int, impressions: int) -> None:
    """Update keyword stats with engagement data."""
    stats = get_keyword_stats(keyword) or KeywordStats(keyword=keyword)
    stats.successes += 1
    stats.total_likes += likes
    stats.total_impressions += impressions
    stats.last_success = datetime.utcnow()
    upsert_keyword_stats(stats)
    log.info("Updated keyword '%s': +%d likes, +%d impressions", keyword, likes, impressions)
