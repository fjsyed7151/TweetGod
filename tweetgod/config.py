from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    # Twitter API
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""
    twitter_bearer_token: str = ""

    # xAI (Grok)
    xai_api_key: str = ""
    xai_model: str = "grok-4-1-fast-non-reasoning"

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Apify
    apify_api_token: str = ""

    # Sentry
    sentry_dsn: str = ""

    # --- Bot behaviour ---

    # Daily post limit (free tier = 500/month ≈ 16/day)
    daily_post_limit: int = 12

    # Active hours (US Central / CT)
    active_hour_start: int = 10  # 10 AM CT
    active_hour_end: int = 18    # 6 PM CT
    timezone: str = "US/Central"

    # Scheduler jitter (minutes)
    schedule_interval_min: int = 25
    schedule_interval_max: int = 55

    # Scraping
    tweets_per_run: int = 40
    max_tweet_age_hours: int = 6  # Only tweets from last 6 hours
    top_n_candidates: int = 5

    # Quality filter thresholds (adaptive — these are base minimums)
    min_text_length: int = 60
    min_followers: int = 100
    min_replies: int = 3
    min_likes: int = 5
    min_views: int = 100

    # Quote tweet constraints
    max_quote_length: int = 280
    min_quote_length: int = 30

    # Priority accounts (reply guy mode)
    priority_account_chance: float = 0.55
    priority_score_boost: float = 1.20
    max_replies_per_author_per_day: int = 1
    priority_max_age_hours: int = 2
    priority_sample_size: int = 18

    # Trending / viral detection
    trending_chance: float = 0.30
    trending_tweets_per_run: int = 90
    trending_max_age_hours: int = 4
    trending_min_velocity: float = 15.0
    trending_min_followers: int = 500

    # Community search
    community_chance: float = 0.05

    # Approval flow
    require_approval: bool = True
    approval_timeout_minutes: int = 60

    # Retry
    max_retries: int = 3

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()


# ── Persona ──────────────────────────────────────────────────────────────────
# CUSTOMIZE THIS: Replace with your own name, bio, and voice description.
# This is what Grok uses to understand your voice when polishing tweets.

PERSONA = {
    "name": "Your Name",
    "bio": (
        "Your bio here. Include your background, what you do, and what "
        "you're known for. This helps the LLM understand your voice."
    ),
    "voice": (
        "Describe how you write. Are you casual or formal? Direct or nuanced? "
        "Do you use humor? What phrases do you avoid? Be specific — the more "
        "detail here, the better Grok preserves your actual voice."
    ),
}


# ── Keywords & Communities ───────────────────────────────────────────────────
# CUSTOMIZE THIS: Replace with keywords relevant to YOUR niche.
# These are the search terms the bot uses to find tweets worth engaging with.
# Tip: Ask Claude Code to help you brainstorm keywords for your niche.

KEYWORDS: list[str] = [
    # Your core tools/topics (what you teach or work with)
    "your tool 1",
    "your tool 2",
    "your topic 1",
    # Your audience's interests (what they care about)
    "audience interest 1",
    "audience interest 2",
    "audience interest 3",
]

TRENDING_KEYWORDS: list[str] = [
    # Broader terms for catching viral conversations in your space.
    # Keep these more general than your regular keywords.
    "broad topic 1",
    "broad topic 2",
    "broad topic 3",
]

# ── Watchlist (Optional) ────────────────────────────────────────────────────
# Accounts you want INSTANT alerts for when they tweet about specific topics.
# Great for staying on top of product announcements or key voices.
# Remove or leave empty if you don't need this feature.

WATCHLIST_ACCOUNTS: list[str] = [
    # "username1",     # Description of why you watch them
    # "username2",     # Description of why you watch them
]

WATCHLIST_KEYWORDS: list[str] = [
    # Keywords to match in watchlist account tweets.
    # Only tweets containing these trigger an alert.
    # "keyword1",
    # "keyword2",
]

COMMUNITY_IDS: list[str] = [
    # X Community IDs to monitor (optional).
    # Find the ID in the community URL: x.com/i/communities/<ID>
]

# ── Priority Accounts ───────────────────────────────────────────────────────
# CUSTOMIZE THIS: The big accounts in YOUR niche you want to quote-tweet.
# The bot checks their recent tweets 55% of the time.
# Pick 20-40 accounts with large, engaged audiences in your space.
# Tip: Ask Claude Code "Who are the top 30 Twitter accounts in [your niche]?"

PRIORITY_ACCOUNTS: list[str] = [
    # ── Big accounts (100K+ followers) ──
    # "username1",     # Name — why they matter
    # "username2",     # Name — why they matter
    # ── Mid-tier accounts (10K-100K) — often engage back ──
    # "username3",     # Name — why they matter
    # "username4",     # Name — why they matter
    # ── Official/brand accounts ──
    # "username5",     # Brand — official account
]
