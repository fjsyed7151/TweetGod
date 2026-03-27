"""Integration test — dry-run pipeline without real API calls."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from tweetgod.models import Tweet, ScoredTweet
from tweetgod.approval import ApprovalResult
from tweetgod.main import run_pipeline


def _make_tweets(n: int = 5) -> list[Tweet]:
    return [
        Tweet(
            tweet_id=str(1000 + i),
            text=f"This is a test tweet about AI agents and LLMs number {i} with enough length to pass filters",
            author_username=f"user{i}",
            author_followers=5000 + i * 1000,
            likes=20 + i * 10,
            retweets=5 + i * 2,
            replies=4 + i,
            views=1000 + i * 500,
            created_at=datetime.utcnow() - timedelta(hours=1 + i * 0.5),
            language="en",
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_dry_run_pipeline():
    """Full pipeline in dry-run mode — should not post anything."""
    tweets = _make_tweets()
    approval = ApprovalResult(
        outcome="approved",
        final_text="test quote tweet",
        raw_input="test raw input",
    )

    with (
        patch("tweetgod.main.get_today_post_count", return_value=0),
        patch("tweetgod.main._is_active_hours", return_value=True),
        patch("tweetgod.main.get_all_keyword_stats", return_value={}),
        patch("tweetgod.main.increment_keyword_attempt"),
        patch("tweetgod.main.scrape_tweets", new_callable=AsyncMock, return_value=tweets),
        patch("tweetgod.main.get_replied_tweet_ids", return_value=set()),
        patch("tweetgod.main.get_today_replied_authors", return_value=set()),
        patch("tweetgod.main.request_approval", new_callable=AsyncMock, return_value=approval),
        patch("tweetgod.main.save_review"),
        patch("tweetgod.main.notify_no_tweets", new_callable=AsyncMock),
    ):
        result = await run_pipeline(dry_run=True)
        assert result is None  # dry run never returns a PostedQuote


@pytest.mark.asyncio
async def test_pipeline_respects_daily_limit():
    """Pipeline should bail when daily limit is reached."""
    with (
        patch("tweetgod.main._is_active_hours", return_value=True),
        patch("tweetgod.main.get_today_post_count", return_value=999),
        patch("tweetgod.main.notify_daily_limit", new_callable=AsyncMock) as mock_notify,
    ):
        result = await run_pipeline()
        assert result is None
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_skips_outside_active_hours():
    """Pipeline should skip outside active hours."""
    with patch("tweetgod.main._is_active_hours", return_value=False):
        result = await run_pipeline()
        assert result is None


@pytest.mark.asyncio
async def test_pipeline_handles_no_tweets():
    """Pipeline should notify when scraper returns nothing."""
    with (
        patch("tweetgod.main._is_active_hours", return_value=True),
        patch("tweetgod.main.get_today_post_count", return_value=0),
        patch("tweetgod.main.get_all_keyword_stats", return_value={}),
        patch("tweetgod.main.increment_keyword_attempt"),
        patch("tweetgod.main.scrape_tweets", new_callable=AsyncMock, return_value=[]),
        patch("tweetgod.main.notify_no_tweets", new_callable=AsyncMock) as mock_notify,
        patch("asyncio.sleep", new_callable=AsyncMock),  # skip retry waits
    ):
        result = await run_pipeline()
        assert result is None
        mock_notify.assert_called_once()
