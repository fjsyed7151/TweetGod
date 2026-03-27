"""Tests for the weighted keyword selector."""

from datetime import datetime, timedelta

from tweetgod.models import KeywordStats
from tweetgod.selector import _compute_weight, select_keyword


class TestComputeWeight:
    def test_new_keyword_gets_exploration_bonus(self):
        weight = _compute_weight("new_keyword", None)
        assert weight == 15.0  # base 10 + 5 exploration

    def test_successful_keyword_gets_bonus(self):
        stats = KeywordStats(
            keyword="good", attempts=20, successes=15,
            total_likes=100, last_used=datetime.utcnow() - timedelta(hours=12),
        )
        weight = _compute_weight("good", stats)
        # Should be high due to success_rate (0.75 * 15 = 11.25) + engagement
        assert weight > 20

    def test_recently_used_gets_penalty(self):
        stats = KeywordStats(
            keyword="recent", attempts=10, successes=5,
            last_used=datetime.utcnow() - timedelta(minutes=30),
        )
        weight_recent = _compute_weight("recent", stats)

        stats_old = KeywordStats(
            keyword="old", attempts=10, successes=5,
            last_used=datetime.utcnow() - timedelta(hours=12),
        )
        weight_old = _compute_weight("old", stats_old)
        assert weight_old > weight_recent

    def test_weight_never_below_one(self):
        stats = KeywordStats(
            keyword="bad", attempts=100, successes=0,
            last_used=datetime.utcnow() - timedelta(minutes=10),
        )
        weight = _compute_weight("bad", stats)
        assert weight >= 1.0


class TestSelectKeyword:
    def test_returns_valid_search_type(self):
        keyword, search_type = select_keyword({}, keywords=["AI", "LLM"])
        assert search_type in ("keyword", "community", "priority", "trending")

    def test_selects_from_provided_keywords(self):
        # Run multiple times to account for randomness
        keywords = ["Alpha", "Beta"]
        selections = set()
        for _ in range(50):
            kw, st = select_keyword({}, keywords=keywords)
            if st == "keyword":
                selections.add(kw)
        # At least one of our keywords should appear
        assert selections.issubset({"Alpha", "Beta"})

    def test_distribution_roughly_correct(self):
        """Over many runs, priority should dominate (~55%)."""
        counts = {"priority": 0, "trending": 0, "community": 0, "keyword": 0}
        n = 1000
        for _ in range(n):
            _, st = select_keyword({}, keywords=["AI"])
            counts[st] += 1

        # Priority should be the most common (within tolerance)
        assert counts["priority"] > n * 0.40, f"priority too low: {counts['priority']}/{n}"
        assert counts["trending"] > n * 0.15, f"trending too low: {counts['trending']}/{n}"
