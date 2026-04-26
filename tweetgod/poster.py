"""Quote tweet posting via Typefully API v2.

Replaces the previous direct Twitter API integration. Uses Typefully's
draft+publish flow with `publish_at: "now"` to post immediately, and
`x.settings.quote_post_url` to attach the original tweet as a quote.

Notes on `quote_tweet_id` semantics in PostedQuote:
- On a fully successful publish where Typefully returns the X URL, we store
  the X status ID (digits only) so engagement_tracker can match cleanly.
- If Typefully publishes asynchronously and the X URL isn't in the response
  yet, we store the Typefully draft id prefixed with "tf:" — engagement_tracker
  resolves the real X URL later via GET /v2/drafts/{id}.
"""

from __future__ import annotations

import logging
import re

import httpx

from tweetgod.config import settings
from tweetgod.models import PostedQuote

log = logging.getLogger(__name__)

TYPEFULLY_BASE = "https://api.typefully.com/v2"

# Cached after first auto-discovery so we don't hit /social-sets every post.
_cached_social_set_id: str | None = None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.typefully_api_key}",
        "Content-Type": "application/json",
    }


def _resolve_social_set_id() -> str | None:
    """Return the configured social_set_id, auto-discovering one if needed.

    Picks the first social set that has X/Twitter enabled.
    """
    global _cached_social_set_id

    if settings.typefully_social_set_id:
        return settings.typefully_social_set_id
    if _cached_social_set_id:
        return _cached_social_set_id

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{TYPEFULLY_BASE}/social-sets", headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.error("Typefully /social-sets fetch failed", exc_info=True)
        return None

    # Response shape per Typefully API: {"data": [{"id": ..., "platforms": {...}}, ...]}
    sets = data.get("data") or data.get("social_sets") or (data if isinstance(data, list) else [])
    for s in sets:
        platforms = s.get("platforms") or {}
        x = platforms.get("x") or platforms.get("twitter") or {}
        if x and (x.get("enabled") or x.get("connected")):
            _cached_social_set_id = str(s["id"])
            log.info("Auto-discovered Typefully social_set_id=%s", _cached_social_set_id)
            return _cached_social_set_id

    # Fallback: first set, X-or-not — better than failing outright
    if sets:
        _cached_social_set_id = str(sets[0]["id"])
        log.warning(
            "No X-enabled social set found; using first set id=%s",
            _cached_social_set_id,
        )
        return _cached_social_set_id

    log.error("Typefully returned zero social sets")
    return None


_X_STATUS_RE = re.compile(r"(?:twitter|x)\.com/[^/]+/status/(\d+)")


def _extract_x_status_id(*candidates: object) -> str | None:
    """Find an X status ID inside any of the given strings."""
    for c in candidates:
        if not isinstance(c, str):
            continue
        m = _X_STATUS_RE.search(c)
        if m:
            return m.group(1)
    return None


def post_quote_tweet(text: str, quoted_tweet_url: str) -> PostedQuote | None:
    """Publish a quote tweet via Typefully. Returns PostedQuote on success."""
    if not settings.typefully_api_key:
        log.error("TYPEFULLY_API_KEY not set")
        return None

    social_set_id = _resolve_social_set_id()
    if not social_set_id:
        return None

    payload = {
        "platforms": {
            "x": {
                "enabled": True,
                "posts": [{"text": text}],
                "settings": {"quote_post_url": quoted_tweet_url},
            }
        },
        "publish_at": "now",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{TYPEFULLY_BASE}/social-sets/{social_set_id}/drafts",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        log.error(
            "Typefully publish failed: %s — %s",
            e.response.status_code,
            e.response.text[:500],
        )
        return None
    except Exception:
        log.error("Typefully publish failed", exc_info=True)
        return None

    # Try to extract the published X URL/ID from the response. Field names vary
    # ("published_url", "url", "x_url", or nested under platforms.x.posts[0]).
    published_url = (
        data.get("published_url")
        or data.get("url")
        or data.get("x_url")
        or _maybe_url_from_platforms(data)
    )
    x_status_id = _extract_x_status_id(published_url, data.get("permalink"))

    draft_id = str(data.get("id") or data.get("draft_id") or "")
    if x_status_id:
        quote_tweet_id = x_status_id
        log.info("Posted quote tweet (X id=%s, draft id=%s)", x_status_id, draft_id)
    elif draft_id:
        quote_tweet_id = f"tf:{draft_id}"
        log.info(
            "Typefully draft accepted (id=%s) — X URL not in immediate response; "
            "engagement_tracker will resolve later",
            draft_id,
        )
    else:
        log.error("Typefully response missing both X URL and draft id: %s", data)
        return None

    return PostedQuote(
        tweet_id="",
        quote_tweet_id=quote_tweet_id,
        author_username="",
        quote_text=text,
    )


def _maybe_url_from_platforms(data: dict) -> str | None:
    platforms = data.get("platforms") or {}
    x = platforms.get("x") or platforms.get("twitter") or {}
    posts = x.get("posts") or []
    if posts and isinstance(posts[0], dict):
        return posts[0].get("published_url") or posts[0].get("url")
    return None
