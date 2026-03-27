"""Tweet scoring engine.

Computes a composite score predicting engagement potential.
Deterministic and testable — no LLM involved.
"""

from __future__ import annotations

import math
import re

from tweetgod.config import settings
from tweetgod.models import Tweet, ScoredTweet

# Patterns that signal a question/discussion-inviting tweet
_QUESTION_PATTERNS = re.compile(
    r"\?|"
    r"\b(?:what do you|how do you|anyone else|who else|thoughts on|"
    r"what's your|whats your|do you think|would you|should we|"
    r"have you|why do|why does|why is|am i the only|is it just me|"
    r"hot take|unpopular opinion|genuine question|serious question)\b",
    re.IGNORECASE,
)


def score_tweet(
    tweet: Tweet,
    replyability: float = 0.0,
    source_type: str = "keyword",
) -> ScoredTweet:
    """Score a tweet for engagement potential.

    Components (when replyability data exists):
      - velocity:      engagement rate relative to tweet age (35%)
      - authority:      author credibility signal (25%)
      - timing:         how fresh the tweet is — fresher = better (15%)
      - opportunity:    reply gap / low competition signal (10%)
      - replyability:   LLM-rated replyability (15%)

    Fallback weights (no replyability):
      - velocity 40%, authority 30%, timing 20%, opportunity 10%

    Bonus: viral ratio (retweets / followers) above threshold.
    """
    velocity = _velocity_score(tweet)
    authority = _authority_score(tweet)
    timing = _timing_score(tweet)
    opportunity = _opportunity_score(tweet)

    if source_type == "trending":
        # Trending mode: velocity is the key signal for viral detection
        if replyability > 0:
            raw = (
                velocity * 0.50
                + authority * 0.20
                + timing * 0.10
                + opportunity * 0.05
                + replyability * 0.15
            )
        else:
            raw = velocity * 0.55 + authority * 0.25 + timing * 0.15 + opportunity * 0.05
    elif replyability > 0:
        raw = (
            velocity * 0.35
            + authority * 0.25
            + timing * 0.15
            + opportunity * 0.10
            + replyability * 0.15
        )
    else:
        raw = velocity * 0.40 + authority * 0.30 + timing * 0.20 + opportunity * 0.10

    # Question/discussion tweet boost: 30% bonus for engagement-inviting tweets
    if _QUESTION_PATTERNS.search(tweet.text):
        raw *= 1.30

    # Viral ratio bonus: RT/follower ratio > 2.16 is viral territory
    viral_ratio = 0.0
    if tweet.author_followers > 0:
        viral_ratio = tweet.retweets / tweet.author_followers
    if viral_ratio > 2.16:
        raw *= 1.25  # 25% bonus for viral tweets

    # Priority account boost
    if source_type == "priority":
        raw *= settings.priority_score_boost

    return ScoredTweet(
        tweet=tweet,
        score=round(raw, 4),
        velocity_score=round(velocity, 4),
        authority_score=round(authority, 4),
        timing_score=round(timing, 4),
        opportunity_score=round(opportunity, 4),
        viral_ratio=round(viral_ratio, 4),
        replyability_score=round(replyability, 4),
        source_type=source_type,
    )


def _velocity_score(tweet: Tweet) -> float:
    """Engagement velocity — likes + retweets per hour, log-scaled."""
    age = max(tweet.age_hours, 0.1)  # avoid division by zero
    engagements_per_hour = (tweet.likes + tweet.retweets) / age
    # log2 scaling: 1 eng/hr → 0, 8 eng/hr → 3, 64 eng/hr → 6
    return min(math.log2(max(engagements_per_hour, 1)), 10.0)


def _authority_score(tweet: Tweet) -> float:
    """Author reputation — followers log-scaled, capped at 10."""
    if tweet.author_followers <= 0:
        return 0.0
    # log10: 1k → 3, 10k → 4, 100k → 5, 1M → 6
    return min(math.log10(tweet.author_followers), 10.0)


def _timing_score(tweet: Tweet) -> float:
    """Freshness bonus — strongly favours recent tweets.

    < 1h  → 10
    1-3h  → 7-9
    3-6h  → 4-6
    > 6h  → rapidly drops
    """
    age = tweet.age_hours
    if age <= 0.1:
        return 10.0
    # Exponential decay: half-life of ~2 hours
    return max(10.0 * math.exp(-0.35 * age), 0.0)


def _opportunity_score(tweet: Tweet) -> float:
    """Reply gap — tweets with few replies relative to likes are underserved.

    High likes but low replies = big opportunity for visibility.
    """
    if tweet.likes == 0:
        return 0.0
    ratio = tweet.replies / max(tweet.likes, 1)
    # Low ratio = high opportunity (inverted, scaled 0-10)
    if ratio < 0.1:
        return 10.0
    elif ratio < 0.3:
        return 7.0
    elif ratio < 0.5:
        return 4.0
    else:
        return 1.0


def rank_tweets(
    tweets: list[Tweet],
    top_n: int = 5,
    replyability_scores: dict[str, float] | None = None,
    source_type: str = "keyword",
) -> list[ScoredTweet]:
    """Score and rank tweets, returning the top N."""
    scores = replyability_scores or {}
    scored = [
        score_tweet(t, replyability=scores.get(t.tweet_id, 0.0), source_type=source_type)
        for t in tweets
    ]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_n]
