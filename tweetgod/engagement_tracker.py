"""Engagement tracker — the feedback loop, via Typefully analytics.

Replaces the previous Twitter API integration. For each row in
`replied_tweets` posted ~24h ago that hasn't been checked yet:

1. If the stored quote_tweet_id is a Typefully draft id (prefix "tf:"),
   resolve it to the real X URL / status id via GET /v2/drafts/{id}.
2. Look up the post in Typefully's analytics endpoint, read likes and
   impressions, write them back to Supabase, and update keyword stats.

Defensive about Typefully response shapes since the v2 analytics schema
isn't fully published. Anything we can't parse is logged and skipped, never
crashes the scheduler.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import httpx

from tweetgod.config import settings
from tweetgod.dedup import (
    _get_client as get_supabase,
    get_keyword_stats,
    upsert_keyword_stats,
)
from tweetgod.models import KeywordStats

log = logging.getLogger(__name__)

TYPEFULLY_BASE = "https://api.typefully.com/v2"

_X_STATUS_RE = re.compile(r"(?:twitter|x)\.com/[^/]+/status/(\d+)")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.typefully_api_key}",
        "Content-Type": "application/json",
    }


def _extract_x_status_id(s: str | None) -> str | None:
    if not s:
        return None
    m = _X_STATUS_RE.search(s)
    return m.group(1) if m else None


def _resolve_draft(draft_id: str) -> str | None:
    """Given a Typefully draft id, return the published X status id (or None)."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{TYPEFULLY_BASE}/drafts/{draft_id}", headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.warning("Failed to resolve Typefully draft %s", draft_id, exc_info=True)
        return None

    url = (
        data.get("x_published_url")
        or data.get("published_url")
        or data.get("url")
        or _url_from_platforms(data)
    )
    return _extract_x_status_id(url)


def _url_from_platforms(data: dict) -> str | None:
    platforms = data.get("platforms") or {}
    x = platforms.get("x") or platforms.get("twitter") or {}
    posts = x.get("posts") or []
    if posts and isinstance(posts[0], dict):
        return posts[0].get("published_url") or posts[0].get("url")
    return None


def _fetch_analytics_posts() -> list[dict]:
    """Fetch recent post analytics from Typefully.

    Endpoint shape inferred from Typefully's MCP/agent-skill toolkit
    (`list_social_set_analytics_posts`). Returns a list of post dicts each
    expected to carry an X URL/id and engagement metrics. Empty list on error.
    """
    social_set_id = settings.typefully_social_set_id
    if not social_set_id:
        # poster.py caches discovered id at module level — import lazily.
        from tweetgod.poster import _resolve_social_set_id
        social_set_id = _resolve_social_set_id() or ""

    if not social_set_id:
        log.warning("No Typefully social_set_id available for analytics")
        return []

    url = f"{TYPEFULLY_BASE}/social-sets/{social_set_id}/analytics/posts"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.warning("Typefully analytics fetch failed", exc_info=True)
        return []

    # Tolerate either {"data": [...]}, {"posts": [...]}, or a bare list.
    if isinstance(data, list):
        return data
    return data.get("data") or data.get("posts") or []


def _metrics_from_post(post: dict) -> tuple[int, int]:
    """Pull (likes, impressions) out of an analytics post dict, defensively."""
    likes = (
        post.get("likes")
        or post.get("like_count")
        or post.get("favorite_count")
        or 0
    )
    impressions = (
        post.get("impressions")
        or post.get("impression_count")
        or post.get("views")
        or post.get("view_count")
        or 0
    )
    return int(likes or 0), int(impressions or 0)


def _post_x_id(post: dict) -> str | None:
    """Find the X status id for a post analytics entry."""
    direct = post.get("x_post_id") or post.get("status_id") or post.get("tweet_id")
    if direct:
        return str(direct)
    for key in ("url", "permalink", "x_url", "published_url"):
        sid = _extract_x_status_id(post.get(key))
        if sid:
            return sid
    return None


async def check_reply_engagement() -> dict:
    """Check engagement on quote tweets posted ~24h ago via Typefully analytics."""
    if not settings.typefully_api_key:
        log.info("TYPEFULLY_API_KEY not set, skipping engagement check")
        return {"checked": 0}

    supabase = get_supabase()
    now = datetime.utcnow()
    window_start = (now - timedelta(hours=28)).isoformat() + "Z"
    window_end = (now - timedelta(hours=20)).isoformat() + "Z"

    resp = (
        supabase.table("replied_tweets")
        .select("*")
        .gte("posted_at", window_start)
        .lte("posted_at", window_end)
        .is_("engagement_checked", "null")
        .execute()
    )

    rows = resp.data or []
    if not rows:
        log.info("No posts to check for engagement")
        return {"checked": 0}

    # Pull all analytics once and build an index by X status id.
    analytics_index: dict[str, dict] = {}
    for post in _fetch_analytics_posts():
        sid = _post_x_id(post)
        if sid:
            analytics_index[sid] = post

    results = {"checked": 0, "with_engagement": 0, "total_likes": 0}

    for row in rows:
        stored_id = row.get("reply_tweet_id") or ""
        if not stored_id:
            continue

        # Resolve Typefully draft id to real X status id if needed.
        if stored_id.startswith("tf:"):
            x_id = _resolve_draft(stored_id[3:])
            if not x_id:
                log.info("Draft %s not yet published, will retry next cycle", stored_id)
                continue
            # Persist the resolved id so we don't re-resolve.
            supabase.table("replied_tweets").update(
                {"reply_tweet_id": x_id}
            ).eq("reply_tweet_id", stored_id).execute()
            stored_id = x_id

        post = analytics_index.get(stored_id)
        if post is None:
            log.debug("No Typefully analytics entry for %s yet", stored_id)
            continue

        likes, impressions = _metrics_from_post(post)
        if not impressions and likes > 0:
            impressions = likes * 100  # same fallback estimate as before

        results["checked"] += 1
        results["total_likes"] += likes

        supabase.table("replied_tweets").update(
            {
                "engagement_likes": likes,
                "engagement_impressions": impressions,
                "engagement_checked": now.isoformat(),
            }
        ).eq("reply_tweet_id", stored_id).execute()

        keyword = row.get("keyword", "")
        eng_rate = likes / impressions if impressions > 0 else 0.0
        success = eng_rate >= 0.005

        if success:
            results["with_engagement"] += 1
        if keyword and (success or likes > 0):
            _update_keyword_success(keyword, likes, impressions)

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
