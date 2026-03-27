"""Tweet quality filter.

Three-tier filtering:
  - Priority: dedup, language, text length, age, no-promo (skip engagement floors)
  - Trending: dedup, language, text length, age, min followers, velocity check
  - Keyword: adaptive thresholds with age adjustment (original behaviour)
"""

from __future__ import annotations

import logging
import re

from tweetgod.config import settings
from tweetgod.models import Tweet

log = logging.getLogger(__name__)

# Promo patterns — reject tweets that are mostly promotional
_PROMO_PATTERNS = re.compile(
    r"\b(giveaway|contest|subscribe|retweet to win|drop your wallet|airdrop)\b",
    re.IGNORECASE,
)


def passes_quality_filter(
    tweet: Tweet,
    already_replied: set[str],
    search_type: str = "keyword",
) -> bool:
    """Return True if the tweet passes all quality checks."""
    reasons = []

    # ── Universal checks ──
    if tweet.tweet_id in already_replied:
        reasons.append("already replied")

    if tweet.language != "en":
        reasons.append(f"language={tweet.language}")

    if len(tweet.text) < settings.min_text_length:
        reasons.append(f"text too short ({len(tweet.text)} chars)")

    # ── Priority mode ──
    if search_type == "priority":
        if tweet.age_hours > settings.priority_max_age_hours:
            reasons.append(f"too old ({tweet.age_hours:.1f}h, max {settings.priority_max_age_hours}h)")

        if tweet.author_followers < settings.min_followers:
            reasons.append(f"followers={tweet.author_followers}")

        if _is_promo(tweet.text):
            reasons.append("promotional content")

    # ── Trending mode (velocity-based viral detection) ──
    elif search_type == "trending":
        if tweet.age_hours > settings.trending_max_age_hours:
            reasons.append(f"too old ({tweet.age_hours:.1f}h, max {settings.trending_max_age_hours}h)")

        if tweet.author_followers < settings.trending_min_followers:
            reasons.append(f"followers={tweet.author_followers} (need {settings.trending_min_followers})")

        # Velocity check: (likes + RTs) / age_hours
        age = max(tweet.age_hours, 0.1)
        velocity = (tweet.likes + tweet.retweets) / age
        if velocity < settings.trending_min_velocity:
            reasons.append(f"velocity={velocity:.1f}/hr (need {settings.trending_min_velocity})")

    # ── Keyword & community mode (original adaptive thresholds) ──
    else:
        if tweet.author_followers < settings.min_followers:
            reasons.append(f"followers={tweet.author_followers}")

        age = tweet.age_hours
        age_factor = _age_adjustment(age)

        adjusted_likes = settings.min_likes * age_factor
        adjusted_views = settings.min_views * age_factor
        adjusted_replies = settings.min_replies * age_factor

        if tweet.likes < adjusted_likes:
            reasons.append(f"likes={tweet.likes} (need {adjusted_likes:.0f})")

        if tweet.views < adjusted_views:
            reasons.append(f"views={tweet.views} (need {adjusted_views:.0f})")

        if tweet.replies < adjusted_replies:
            reasons.append(f"replies={tweet.replies} (need {adjusted_replies:.0f})")

        if age > settings.max_tweet_age_hours:
            reasons.append(f"too old ({age:.1f}h)")

    if reasons:
        log.debug("Filtered out @%s [%s]: %s", tweet.author_username, search_type, ", ".join(reasons))
        return False
    return True


def _is_promo(text: str) -> bool:
    """Detect promotional / link-heavy tweets."""
    # Check for promo keywords
    if _PROMO_PATTERNS.search(text):
        return True

    # Reject tweets that are mostly URLs (more than 40% of text is URLs)
    url_chars = sum(len(m) for m in re.findall(r"https?://\S+", text))
    if len(text) > 0 and url_chars / len(text) > 0.40:
        return True

    return False


def _age_adjustment(age_hours: float) -> float:
    """Lower the engagement threshold for very fresh tweets.

    < 1h  → 0.3x (a tweet only needs 30% of base thresholds)
    1-2h  → 0.5x
    2-4h  → 0.75x
    4-6h  → 1.0x (full thresholds apply)
    """
    if age_hours < 1:
        return 0.3
    elif age_hours < 2:
        return 0.5
    elif age_hours < 4:
        return 0.75
    else:
        return 1.0


def filter_tweets(
    tweets: list[Tweet],
    already_replied: set[str],
    search_type: str = "keyword",
) -> list[Tweet]:
    """Apply quality filter to a list of tweets."""
    passed = [t for t in tweets if passes_quality_filter(t, already_replied, search_type)]
    log.info("Quality filter [%s]: %d/%d tweets passed", search_type, len(passed), len(tweets))
    return passed


def apply_diversity_filter(tweets: list[Tweet], replied_authors_today: set[str]) -> list[Tweet]:
    """Remove tweets from authors we've already replied to today.

    Enforces max_replies_per_author_per_day = 1 by filtering out
    any tweet whose author is in the already-replied set.
    """
    filtered = [t for t in tweets if t.author_username not in replied_authors_today]
    removed = len(tweets) - len(filtered)
    if removed:
        log.info("Diversity filter: removed %d tweets from already-replied authors", removed)
    return filtered
