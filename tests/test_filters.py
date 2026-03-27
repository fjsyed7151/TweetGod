"""Tests for the quality filter."""

from datetime import datetime, timedelta

from tweetgod.models import Tweet
from tweetgod.filters import (
    passes_quality_filter,
    filter_tweets,
    _age_adjustment,
    _is_promo,
)


def _make_tweet(**kwargs) -> Tweet:
    defaults = {
        "tweet_id": "123",
        "text": "A" * 80,  # 80 chars, above min_text_length
        "author_username": "testuser",
        "author_followers": 500,
        "likes": 20,
        "retweets": 5,
        "replies": 5,
        "views": 500,
        "created_at": datetime.utcnow() - timedelta(hours=2),
        "language": "en",
    }
    defaults.update(kwargs)
    return Tweet(**defaults)


class TestPassesQualityFilter:
    def test_good_tweet_passes(self):
        tweet = _make_tweet()
        assert passes_quality_filter(tweet, set()) is True

    def test_already_replied_fails(self):
        tweet = _make_tweet(tweet_id="already_done")
        assert passes_quality_filter(tweet, {"already_done"}) is False

    def test_non_english_fails(self):
        tweet = _make_tweet(language="ja")
        assert passes_quality_filter(tweet, set()) is False

    def test_short_text_fails(self):
        tweet = _make_tweet(text="Too short")
        assert passes_quality_filter(tweet, set()) is False

    def test_low_followers_fails(self):
        tweet = _make_tweet(author_followers=10)
        assert passes_quality_filter(tweet, set()) is False

    def test_old_tweet_fails(self):
        tweet = _make_tweet(created_at=datetime.utcnow() - timedelta(hours=10))
        assert passes_quality_filter(tweet, set()) is False

    def test_fresh_tweet_with_low_likes_passes(self):
        """A very fresh tweet should have lower engagement thresholds."""
        tweet = _make_tweet(
            likes=2,  # Below base min_likes=5
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        # At 0.5h age, factor = 0.3, so threshold = 5 * 0.3 = 1.5 → 2 likes passes
        assert passes_quality_filter(tweet, set()) is True

    def test_old_tweet_needs_full_engagement(self):
        """An older tweet needs to meet full thresholds."""
        tweet = _make_tweet(
            likes=3,  # Above 0.3x threshold but below 1.0x threshold of 5
            created_at=datetime.utcnow() - timedelta(hours=5),
        )
        assert passes_quality_filter(tweet, set()) is False


class TestPriorityMode:
    def test_priority_skips_engagement_thresholds(self):
        """Priority mode should pass fresh tweets even with 0 likes."""
        tweet = _make_tweet(
            likes=0, retweets=0, replies=0, views=0,
            author_followers=10000,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        assert passes_quality_filter(tweet, set(), search_type="priority") is True

    def test_priority_rejects_old_tweets(self):
        """Priority mode uses priority_max_age_hours (2h)."""
        tweet = _make_tweet(
            author_followers=10000,
            created_at=datetime.utcnow() - timedelta(hours=3),
        )
        assert passes_quality_filter(tweet, set(), search_type="priority") is False

    def test_priority_rejects_promo(self):
        tweet = _make_tweet(
            text="Check out our GIVEAWAY for a chance to win an AI course! " + "A" * 40,
            author_followers=10000,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        assert passes_quality_filter(tweet, set(), search_type="priority") is False


class TestTrendingMode:
    def test_trending_passes_high_velocity(self):
        """A tweet with 30 likes in 30 min = 60/hr, well above threshold."""
        tweet = _make_tweet(
            likes=25, retweets=5,
            author_followers=1000,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        assert passes_quality_filter(tweet, set(), search_type="trending") is True

    def test_trending_rejects_low_velocity(self):
        """50 likes in 6 hours = 8.3/hr, below 15.0 threshold."""
        tweet = _make_tweet(
            likes=40, retweets=10,
            author_followers=1000,
            created_at=datetime.utcnow() - timedelta(hours=3.5),
        )
        # velocity = 50 / 3.5 = 14.3 < 15.0
        assert passes_quality_filter(tweet, set(), search_type="trending") is False

    def test_trending_rejects_low_followers(self):
        tweet = _make_tweet(
            likes=100, retweets=50,
            author_followers=100,  # below trending_min_followers=500
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        assert passes_quality_filter(tweet, set(), search_type="trending") is False

    def test_trending_rejects_old_tweets(self):
        """Trending uses trending_max_age_hours (4h)."""
        tweet = _make_tweet(
            likes=200, retweets=100,
            author_followers=5000,
            created_at=datetime.utcnow() - timedelta(hours=5),
        )
        assert passes_quality_filter(tweet, set(), search_type="trending") is False


class TestIsPromo:
    def test_giveaway(self):
        assert _is_promo("Big GIVEAWAY! RT to win!") is True

    def test_contest(self):
        assert _is_promo("Join our contest for free stuff") is True

    def test_normal_text(self):
        assert _is_promo("Just shipped a new feature using Claude Code") is False

    def test_link_heavy(self):
        text = "Check https://example.com/very/long/path/to/something out!"
        # URL is ~49 chars out of ~57 total = ~86%
        assert _is_promo(text) is True

    def test_normal_with_link(self):
        text = "Great article about AI agents and the future of coding https://t.co/abc"
        assert _is_promo(text) is False


class TestAgeAdjustment:
    def test_very_fresh(self):
        assert _age_adjustment(0.5) == 0.3

    def test_one_hour(self):
        assert _age_adjustment(1.5) == 0.5

    def test_three_hours(self):
        assert _age_adjustment(3.0) == 0.75

    def test_old(self):
        assert _age_adjustment(5.0) == 1.0


class TestFilterTweets:
    def test_filters_correctly(self):
        good = _make_tweet(tweet_id="good")
        bad = _make_tweet(tweet_id="bad", language="fr")
        result = filter_tweets([good, bad], set())
        assert len(result) == 1
        assert result[0].tweet_id == "good"

    def test_empty_input(self):
        assert filter_tweets([], set()) == []

    def test_filter_tweets_passes_search_type(self):
        """filter_tweets should forward search_type to passes_quality_filter."""
        tweet = _make_tweet(
            likes=0, retweets=0, replies=0, views=0,
            author_followers=10000,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        # Should fail in keyword mode (low engagement)
        assert filter_tweets([tweet], set(), search_type="keyword") == []
        # Should pass in priority mode (skips engagement)
        result = filter_tweets([tweet], set(), search_type="priority")
        assert len(result) == 1
