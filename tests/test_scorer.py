"""Tests for the scoring engine."""

from datetime import datetime, timedelta

from tweetgod.models import Tweet
from tweetgod.scorer import score_tweet, rank_tweets


def _make_tweet(**kwargs) -> Tweet:
    defaults = {
        "tweet_id": "123",
        "text": "Test tweet about AI agents and their future in software development",
        "author_username": "testuser",
        "author_followers": 5000,
        "likes": 50,
        "retweets": 10,
        "replies": 5,
        "views": 1000,
        "created_at": datetime.utcnow() - timedelta(hours=1),
        "language": "en",
    }
    defaults.update(kwargs)
    return Tweet(**defaults)


class TestScoreTweet:
    def test_basic_scoring(self):
        tweet = _make_tweet()
        scored = score_tweet(tweet)
        assert scored.score > 0
        assert scored.velocity_score > 0
        assert scored.authority_score > 0
        assert scored.timing_score > 0

    def test_fresh_tweet_scores_higher(self):
        fresh = _make_tweet(created_at=datetime.utcnow() - timedelta(minutes=15))
        old = _make_tweet(created_at=datetime.utcnow() - timedelta(hours=5))

        fresh_score = score_tweet(fresh)
        old_score = score_tweet(old)
        assert fresh_score.timing_score > old_score.timing_score

    def test_high_followers_scores_higher_authority(self):
        big = _make_tweet(author_followers=100_000)
        small = _make_tweet(author_followers=500)

        big_score = score_tweet(big)
        small_score = score_tweet(small)
        assert big_score.authority_score > small_score.authority_score

    def test_high_engagement_velocity(self):
        hot = _make_tweet(
            likes=200, retweets=50,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        cold = _make_tweet(
            likes=10, retweets=1,
            created_at=datetime.utcnow() - timedelta(hours=5),
        )

        hot_score = score_tweet(hot)
        cold_score = score_tweet(cold)
        assert hot_score.velocity_score > cold_score.velocity_score

    def test_opportunity_score_high_when_few_replies(self):
        underserved = _make_tweet(likes=100, replies=2)  # ratio 0.02
        saturated = _make_tweet(likes=100, replies=80)   # ratio 0.8

        u_score = score_tweet(underserved)
        s_score = score_tweet(saturated)
        assert u_score.opportunity_score > s_score.opportunity_score

    def test_viral_ratio_bonus(self):
        # RT/follower ratio > 2.16 triggers 25% bonus
        viral = _make_tweet(author_followers=10, retweets=30)  # ratio = 3.0
        normal = _make_tweet(author_followers=10000, retweets=5)  # ratio = 0.0005

        viral_score = score_tweet(viral)
        normal_score = score_tweet(normal)
        assert viral_score.viral_ratio > 2.16
        assert normal_score.viral_ratio < 2.16

    def test_zero_followers_no_crash(self):
        tweet = _make_tweet(author_followers=0)
        scored = score_tweet(tweet)
        assert scored.authority_score == 0.0
        assert scored.viral_ratio == 0.0

    def test_no_created_at_treated_as_old(self):
        tweet = _make_tweet(created_at=None)
        scored = score_tweet(tweet)
        assert scored.timing_score < 1.0


class TestRankTweets:
    def test_returns_top_n(self):
        tweets = [_make_tweet(tweet_id=str(i), likes=i * 10) for i in range(10)]
        ranked = rank_tweets(tweets, top_n=3)
        assert len(ranked) == 3

    def test_highest_scored_first(self):
        tweets = [
            _make_tweet(tweet_id="low", likes=5, views=100),
            _make_tweet(tweet_id="high", likes=500, retweets=100, views=50000),
        ]
        ranked = rank_tweets(tweets, top_n=2)
        assert ranked[0].tweet.tweet_id == "high"

    def test_empty_list(self):
        ranked = rank_tweets([], top_n=5)
        assert ranked == []
