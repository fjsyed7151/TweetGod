"""Weighted keyword/community selector.

Picks which keyword to search for next based on real performance data
from Supabase, with exploration bonuses for under-tried keywords.

Probability routing:
  Priority (55%) → Trending (30%) → Community (5%) → Keyword (10%)
"""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime

from tweetgod.config import (
    KEYWORDS,
    COMMUNITY_IDS,
    PRIORITY_ACCOUNTS,
    TRENDING_KEYWORDS,
    settings,
)
from tweetgod.models import KeywordStats

log = logging.getLogger(__name__)


def select_keyword(
    all_stats: dict[str, KeywordStats],
    keywords: list[str] | None = None,
) -> tuple[str, str]:
    """Select a keyword using weighted random selection.

    Returns (keyword, search_type) where search_type is
    "priority" | "trending" | "community" | "keyword".
    """
    if keywords is None:
        keywords = KEYWORDS

    roll = random.random()

    # Priority account chance (55%)
    if PRIORITY_ACCOUNTS and roll < settings.priority_account_chance:
        log.info("Selected priority account scrape")
        return "__priority__", "priority"

    # Trending chance (30%)
    if roll < settings.priority_account_chance + settings.trending_chance:
        keyword = random.choice(TRENDING_KEYWORDS)
        log.info("Selected trending keyword: '%s'", keyword)
        return keyword, "trending"

    # Community chance (5%)
    if COMMUNITY_IDS and roll < (
        settings.priority_account_chance
        + settings.trending_chance
        + settings.community_chance
    ):
        community = random.choice(COMMUNITY_IDS)
        log.info("Selected community: %s", community)
        return community, "community"

    # Keyword (remaining ~10%)
    weights = [_compute_weight(kw, all_stats.get(kw)) for kw in keywords]
    total = sum(weights)
    if total == 0:
        chosen = random.choice(keywords)
    else:
        chosen = random.choices(keywords, weights=weights, k=1)[0]

    log.info("Selected keyword: '%s' (weight %.2f)", chosen, weights[keywords.index(chosen)])
    return chosen, "keyword"


def _compute_weight(keyword: str, stats: KeywordStats | None) -> float:
    """Compute selection weight for a keyword.

    Weight = base + success_bonus + exploration_bonus - recency_penalty
    """
    base = 10.0

    if stats is None:
        # Never tried → high exploration bonus
        return base + 5.0

    # Success bonus: more successful keywords get picked more
    success_bonus = stats.success_rate * 15.0

    # Engagement quality bonus: avg likes per success
    engagement_bonus = min(stats.avg_likes * 0.5, 10.0)

    # Exploration bonus: under-tried keywords get a boost (UCB1-inspired)
    total_attempts = max(stats.attempts, 1)
    exploration_bonus = 3.0 * math.sqrt(math.log(max(total_attempts + 10, 11)) / total_attempts)

    # Recency penalty: if used very recently, slight penalty to encourage variety
    recency_penalty = 0.0
    if stats.last_used:
        hours_since = (datetime.utcnow() - stats.last_used).total_seconds() / 3600
        if hours_since < 2:
            recency_penalty = 5.0
        elif hours_since < 6:
            recency_penalty = 2.0

    weight = base + success_bonus + engagement_bonus + exploration_bonus - recency_penalty
    return max(weight, 1.0)  # floor at 1.0 — never fully exclude a keyword
