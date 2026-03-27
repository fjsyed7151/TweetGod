from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class Tweet(BaseModel):
    """A scraped tweet candidate for quoting."""

    tweet_id: str
    text: str
    author_username: str
    author_followers: int = 0
    author_verified: bool = False
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    created_at: datetime | None = None
    language: str = "en"
    url: str = ""

    @property
    def age_hours(self) -> float:
        if self.created_at is None:
            return 999.0
        delta = datetime.utcnow() - self.created_at
        return delta.total_seconds() / 3600


class ScoredTweet(BaseModel):
    """Tweet with a computed engagement-potential score."""

    tweet: Tweet
    score: float = 0.0
    velocity_score: float = 0.0
    authority_score: float = 0.0
    timing_score: float = 0.0
    opportunity_score: float = 0.0
    viral_ratio: float = 0.0
    replyability_score: float = 0.0
    source_type: str = "keyword"


class GeneratedQuote(BaseModel):
    """A polished quote tweet text."""

    tweet_id: str
    quote_text: str
    confidence: float = 0.0
    reasoning: str = ""


class PostedQuote(BaseModel):
    """A quote tweet that was actually posted to Twitter."""

    tweet_id: str
    quote_tweet_id: str = ""
    author_username: str
    quote_text: str
    tweet_url: str = ""
    posted_at: datetime = Field(default_factory=datetime.utcnow)
    keyword_used: str = ""
    score: float = 0.0
    source_type: str = "keyword"


class KeywordStats(BaseModel):
    """Performance stats for a keyword/community."""

    keyword: str
    attempts: int = 0
    successes: int = 0  # replies that got > 0 engagement
    total_likes: int = 0
    total_impressions: int = 0
    last_used: datetime | None = None
    last_success: datetime | None = None

    @field_validator("last_used", "last_success", mode="before")
    @classmethod
    def strip_tz(cls, v: datetime | str | None) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if v.tzinfo is not None:
            v = v.replace(tzinfo=None)
        return v

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts

    @property
    def avg_likes(self) -> float:
        if self.successes == 0:
            return 0.0
        return self.total_likes / self.successes
