"""Twitter API posting via tweepy."""

from __future__ import annotations

import logging

import tweepy

from tweetgod.config import settings
from tweetgod.models import PostedQuote

log = logging.getLogger(__name__)

_client: tweepy.Client | None = None


def _get_client() -> tweepy.Client:
    global _client
    if _client is None:
        _client = tweepy.Client(
            bearer_token=settings.twitter_bearer_token,
            consumer_key=settings.twitter_api_key,
            consumer_secret=settings.twitter_api_secret,
            access_token=settings.twitter_access_token,
            access_token_secret=settings.twitter_access_token_secret,
            wait_on_rate_limit=True,
        )
    return _client


def post_quote_tweet(text: str, tweet_id: str) -> PostedQuote | None:
    """Post a quote tweet. Returns PostedQuote on success, None on failure."""
    client = _get_client()
    try:
        response = client.create_tweet(text=text, quote_tweet_id=tweet_id)
        quote_tweet_id = str(response.data["id"])
        log.info("Posted quote tweet %s quoting %s", quote_tweet_id, tweet_id)
        return PostedQuote(
            tweet_id=tweet_id,
            quote_tweet_id=quote_tweet_id,
            author_username="",
            quote_text=text,
        )
    except tweepy.TweepyException:
        log.error("Failed to post quote tweet for %s", tweet_id, exc_info=True)
        return None


def post_original_tweet(text: str) -> str | None:
    """Post an original tweet. Returns the tweet ID or None."""
    client = _get_client()
    try:
        response = client.create_tweet(text=text)
        tweet_id = str(response.data["id"])
        log.info("Posted original tweet %s", tweet_id)
        return tweet_id
    except tweepy.TweepyException:
        log.error("Failed to post original tweet", exc_info=True)
        return None


def post_thread(tweets: list[str]) -> list[str]:
    """Post a thread (chain of tweets). Returns list of tweet IDs."""
    client = _get_client()
    ids = []
    reply_to = None

    for i, text in enumerate(tweets):
        try:
            response = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
            tweet_id = str(response.data["id"])
            ids.append(tweet_id)
            reply_to = tweet_id
            log.info("Posted thread tweet %d/%d: %s", i + 1, len(tweets), tweet_id)
        except tweepy.TweepyException:
            log.error("Thread broke at tweet %d/%d", i + 1, len(tweets), exc_info=True)
            break

    return ids


def _extract_tweet_id(url: str) -> str:
    """Extract tweet ID from a Twitter URL."""
    parts = url.rstrip("/").split("/")
    return parts[-1]
