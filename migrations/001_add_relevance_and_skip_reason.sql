-- ============================================================================
-- TweetGod migration 001 — add relevance_score + skip_reason to enable
--   the weekly self-improvement digest.
--
-- Run in Supabase SQL Editor → New Query → paste → Run.
-- Idempotent — safe to re-run.
-- ============================================================================

-- 1. relevance_score: the 0-10 score Grok assigned during the LLM relevance
--    pass. Stored on every review so we can track "approved tweets averaged
--    7.4 vs skipped 4.1" trends week over week.
ALTER TABLE reply_reviews
  ADD COLUMN IF NOT EXISTS relevance_score FLOAT;

ALTER TABLE replied_tweets
  ADD COLUMN IF NOT EXISTS relevance_score FLOAT;

-- 2. skip_reason: short code (or empty). Captured from the Telegram approval
--    flow when the user types 5a/5b/5c/5d/3 instead of plain 5. Lets the
--    weekly digest break down WHY tweets were skipped.
--
--    Codes:
--      'off_topic'   (5a)  — wrong niche entirely
--      'too_brief'   (5b)  — finance-adjacent but no substance to react to
--      'wrong_angle' (5c)  — on-topic but nothing to add / wrong stance
--      'promo'       (5d)  — community shoutouts, giveaways, "appreciate
--                            my guy"-style posts, cause campaigns
--      'bad'         (3)   — generic "this one's bad" without a category
--      ''            (5)   — generic skip, no reason given
ALTER TABLE reply_reviews
  ADD COLUMN IF NOT EXISTS skip_reason TEXT DEFAULT '';

-- 3. Index for the digest query (filters reply_reviews by reviewed_at >= 7d ago).
CREATE INDEX IF NOT EXISTS reply_reviews_reviewed_at_idx
  ON reply_reviews (reviewed_at DESC);

-- That's it. Verify with:
--   SELECT column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name IN ('reply_reviews','replied_tweets')
--     AND column_name IN ('relevance_score','skip_reason');
