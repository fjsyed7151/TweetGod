-- ============================================================================
-- TweetGod — Supabase Database Setup
-- ============================================================================
-- Run this in your Supabase project: SQL Editor → New Query → paste → Run.
-- This creates all 4 tables TweetGod needs.
-- ============================================================================

-- 1. replied_tweets — every quote tweet the bot posts + engagement tracking
CREATE TABLE IF NOT EXISTS replied_tweets (
  tweet_id            TEXT PRIMARY KEY,
  reply_tweet_id      TEXT,
  author_username     TEXT NOT NULL,
  reply_text          TEXT NOT NULL,
  tweet_url           TEXT,
  keyword             TEXT,
  score               FLOAT DEFAULT 0,
  posted_at           TIMESTAMPTZ DEFAULT now(),
  engagement_likes    INT,
  engagement_impressions INT,
  engagement_checked  TIMESTAMPTZ,
  reply_style         TEXT,
  source_type         TEXT DEFAULT 'keyword'
);

-- 2. keyword_stats — tracks how well each keyword performs over time
CREATE TABLE IF NOT EXISTS keyword_stats (
  keyword             TEXT PRIMARY KEY,
  attempts            INT DEFAULT 0,
  successes           INT DEFAULT 0,
  total_likes         INT DEFAULT 0,
  total_impressions   INT DEFAULT 0,
  last_used           TIMESTAMPTZ,
  last_success        TIMESTAMPTZ
);

-- 3. style_stats — tracks performance by reply style
CREATE TABLE IF NOT EXISTS style_stats (
  style               TEXT PRIMARY KEY,
  attempts            INT DEFAULT 0,
  successes           INT DEFAULT 0,
  total_likes         INT DEFAULT 0,
  total_impressions   INT DEFAULT 0,
  last_used           TIMESTAMPTZ,
  last_success        TIMESTAMPTZ
);

-- 4. reply_reviews — full audit log of the approval flow
--    (what the user saw, what they typed, what the LLM produced, what happened)
CREATE TABLE IF NOT EXISTS reply_reviews (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tweet_id            TEXT NOT NULL,
  author_username     TEXT,
  tweet_text          TEXT,
  tweet_url           TEXT,
  ai_reply_text       TEXT NOT NULL,
  final_reply_text    TEXT NOT NULL,
  outcome             TEXT CHECK (outcome IN ('approved','edited','rejected','auto_approved')),
  reply_style         TEXT,
  source_type         TEXT,
  score               FLOAT,
  keyword             TEXT,
  reviewed_at         TIMESTAMPTZ DEFAULT now(),
  response_time_seconds INT,
  raw_input           TEXT
);

-- That's it! The watchlist alert deduplication is handled in-memory by the bot.
