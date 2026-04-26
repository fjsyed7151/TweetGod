"""Apify tweet scraping integration.

Supports both keyword search and community search via Apify actors.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

import httpx

from tweetgod.config import settings, PRIORITY_ACCOUNTS, WATCHLIST_ACCOUNTS
from tweetgod.models import Tweet

log = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"

# Apify actor IDs
SEARCH_ACTOR = "apidojo~tweet-scraper"
COMMUNITY_ACTOR = "apidojo~tweet-scraper"


async def scrape_tweets(keyword: str, search_type: str) -> list[Tweet]:
    """Scrape tweets from Apify.

    Args:
        keyword: The search keyword or community ID.
        search_type: "keyword", "community", "priority", or "trending".
    """
    if search_type == "priority":
        return await _scrape_priority_accounts()
    if search_type == "community":
        return await _scrape_community(keyword)
    if search_type == "trending":
        return await _scrape_trending(keyword)
    return await _scrape_keyword(keyword)


async def _scrape_keyword(keyword: str) -> list[Tweet]:
    """Search tweets by keyword via Apify. Excludes reply tweets."""
    since_date = (datetime.utcnow() - timedelta(hours=settings.max_tweet_age_hours)).strftime(
        "%Y-%m-%d"
    )

    payload = {
        "searchTerms": [f"{keyword} lang:en -filter:replies since:{since_date}"],
        "maxItems": settings.tweets_per_run,
    }

    return await _run_actor(SEARCH_ACTOR, payload)


async def _scrape_community(community_id: str) -> list[Tweet]:
    """Scrape community tweets via Apify."""
    payload = {
        "startUrls": [f"https://x.com/i/communities/{community_id}"],
        "maxItems": settings.tweets_per_run,
    }

    return await _run_actor(COMMUNITY_ACTOR, payload)


async def _scrape_trending(keyword: str) -> list[Tweet]:
    """Search tweets by trending keyword with tighter recency window. Excludes reply tweets."""
    since_date = (
        datetime.utcnow() - timedelta(hours=settings.trending_max_age_hours)
    ).strftime("%Y-%m-%d")

    payload = {
        "searchTerms": [f"{keyword} lang:en -filter:replies since:{since_date}"],
        "maxItems": settings.trending_tweets_per_run,
    }

    return await _run_actor(SEARCH_ACTOR, payload)


async def scrape_watchlist() -> list[Tweet]:
    """Scrape recent tweets from Claude Code watchlist accounts.

    Grabs tweets from the last 2 hours from all watchlist accounts.
    Keyword filtering happens downstream — we cast a wide net here.
    """
    if not WATCHLIST_ACCOUNTS:
        return []

    log.info("Scraping %d watchlist accounts: %s", len(WATCHLIST_ACCOUNTS), WATCHLIST_ACCOUNTS)

    since_date = (
        datetime.utcnow() - timedelta(hours=2)
    ).strftime("%Y-%m-%d")

    from_clauses = " OR ".join(f"from:{u}" for u in WATCHLIST_ACCOUNTS)
    search_query = f"({from_clauses}) lang:en since:{since_date}"

    payload = {
        "searchTerms": [search_query],
        "maxItems": 50,
    }

    return await _run_actor(SEARCH_ACTOR, payload)


async def _scrape_priority_accounts() -> list[Tweet]:
    """Scrape recent tweets from priority accounts using search queries."""
    if not PRIORITY_ACCOUNTS:
        return []

    sample_size = min(settings.priority_sample_size, len(PRIORITY_ACCOUNTS))
    accounts = random.sample(PRIORITY_ACCOUNTS, sample_size)
    log.info("Scraping %d priority accounts: %s", len(accounts), accounts)

    since_date = (
        datetime.utcnow() - timedelta(hours=settings.priority_max_age_hours)
    ).strftime("%Y-%m-%d")

    # Build "from:user1 OR from:user2 ..." search query
    from_clauses = " OR ".join(f"from:{u}" for u in accounts)
    search_query = f"({from_clauses}) lang:en since:{since_date}"

    payload = {
        "searchTerms": [search_query],
        "maxItems": settings.tweets_per_run,
    }

    return await _run_actor(SEARCH_ACTOR, payload)


async def _run_actor(actor_id: str, payload: dict) -> list[Tweet]:
    """Run an Apify actor and return parsed tweets."""
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    headers = {"Authorization": f"Bearer {settings.apify_api_token}"}

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, json=payload, headers=headers)
        # Apify may return 200 or 201 from run-sync endpoints — both are success.
        if not resp.is_success:
            log.error("Apify error %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        items = resp.json()

    log.info("Apify returned %d items for actor %s", len(items), actor_id)
    return [_parse_tweet(item) for item in items if _parse_tweet(item) is not None]


def _parse_tweet(item: dict) -> Tweet | None:
    """Parse an Apify result item into a Tweet model."""
    try:
        tweet_id = str(item.get("id") or item.get("tweetId") or item.get("id_str", ""))
        if not tweet_id:
            return None

        # Handle various date formats from Apify
        created_at = None
        raw_date = item.get("createdAt") or item.get("created_at") or item.get("date")
        if raw_date:
            for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    created_at = datetime.strptime(str(raw_date), fmt).replace(tzinfo=None)
                    break
                except ValueError:
                    continue

        author = item.get("author", {}) or {}
        username = (
            author.get("userName")
            or author.get("screen_name")
            or item.get("user", {}).get("screen_name", "unknown")
        )

        return Tweet(
            tweet_id=tweet_id,
            text=item.get("text") or item.get("full_text") or "",
            author_username=username,
            author_followers=author.get("followers") or item.get("user", {}).get("followers_count", 0),
            author_verified=author.get("isBlueVerified", False),
            likes=item.get("likeCount") or item.get("favorite_count", 0),
            retweets=item.get("retweetCount") or item.get("retweet_count", 0),
            replies=item.get("replyCount") or item.get("reply_count", 0),
            views=item.get("viewCount") or item.get("views", 0),
            created_at=created_at,
            language=item.get("lang", "en"),
            url=f"https://twitter.com/{username}/status/{tweet_id}",
        )
    except Exception:
        log.warning("Failed to parse tweet item", exc_info=True)
        return None
