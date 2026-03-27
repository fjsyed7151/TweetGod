<div align="center">

# ⚡ TweetGod

**AI-powered Twitter engagement engine that finds high-potential tweets, generates sharp replies, and learns what works over time.**

Built with Python · xAI Grok · Next.js · Supabase

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![Railway](https://img.shields.io/badge/Railway-Deployed-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app)
[![Vercel](https://img.shields.io/badge/Vercel-Dashboard-000000?style=flat-square&logo=vercel&logoColor=white)](https://vercel.com)

</div>

---

## How It Works

```
  🔍 Search Twitter          🧠 Score & Rank           ✍️ Generate Replies
  (Apify scraper)    →    (5-signal composite)   →    (xAI Grok, 5 styles)
                                                            │
                                                            ▼
  📊 Track Engagement    ←    🐦 Post to Twitter    ←    📱 Telegram Approval
  (24h feedback loop)         (tweepy)                   (pick / edit / skip)
```

TweetGod runs on a **25-55 minute randomized interval** during active hours. It finds tweets worth replying to, generates replies in multiple styles, sends them to Telegram for human review, and posts approved replies. A feedback loop tracks engagement and adjusts strategy over time.

---

## Features

### 🎯 Smart Tweet Discovery
- **4 search modes** — priority accounts (55%), trending (30%), community (5%), keywords (10%)
- **Composite scoring** — velocity, authority, freshness, opportunity, LLM replyability
- **Adaptive thresholds** that relax for fresh tweets
- **Softmax selection** from top 5 candidates for natural variety

### 🎨 Reply Generation
- **5 reply styles** — witty, insightful, contrarian, supportive, quick reaction
- **Bayesian weighting** — styles that perform well get picked more
- **40% daily cap** per style to maintain diversity
- Banned corporate speak (delve, leverage, robust...)
- Length-constrained: 40-200 characters

### 📱 Telegram Approval Flow
- Generates **3 reply options** per tweet with direct link to original
- Pick by number, send custom text, or reject
- 15-minute timeout with auto-approval fallback

### 🔄 Self-Improving Feedback Loop
- Engagement checker runs every 6 hours
- Success metric: likes/impressions >= 0.5%
- **UCB1 exploration** for keyword selection
- Style selection adapts based on engagement rates

### 📊 Analytics Dashboard
- Real-time Next.js dashboard on Vercel
- Overview stats, reply history, keyword performance, style comparison
- 30-day trend lines for replies, likes, and engagement rate

---

## Architecture

```
tweetgod/                          dashboard/
├── main.py          # Pipeline    ├── app/           # Next.js App Router
├── config.py        # Settings    ├── components/    # UI components
├── scraper.py       # Apify       │   ├── overview/
├── scorer.py        # Scoring     │   ├── replies/
├── filters.py       # Quality     │   ├── keywords/
├── llm.py           # xAI Grok    │   └── analytics/
├── selector.py      # UCB1        └── lib/           # Types + data
├── approval.py      # Telegram
├── poster.py        # Twitter
├── dedup.py         # Supabase
├── engagement_tracker.py
├── notifier.py
└── models.py
```

---

## Scoring System

Each tweet gets a composite score from 5 weighted signals:

| Signal | Weight | What It Measures |
|:---|:---:|:---|
| **Velocity** | 35% | Engagement rate per hour (log-scaled) |
| **Authority** | 25% | Author follower count (log-scaled) |
| **Timing** | 15% | Freshness — exponential decay, 2h half-life |
| **Opportunity** | 10% | Low reply-to-like ratio = more visible slot |
| **Replyability** | 15% | LLM pre-screen: how good is the reply angle? |

> **Bonus multipliers:** +30% for questions/discussion tweets, +25% for viral ratio, +20% for priority accounts

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+ (for dashboard)
- Accounts: Twitter API, xAI, Apify, Supabase, Telegram Bot

### Install & Run

```bash
# Install
pip install -e .

# Dry run (no posting)
python -m tweetgod.main --dry-run

# Live
python -m tweetgod.main
```

### Environment Variables

```bash
# Twitter API
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_TOKEN_SECRET=
TWITTER_BEARER_TOKEN=

# xAI Grok
XAI_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Apify
APIFY_API_TOKEN=

# Optional
SENTRY_DSN=
```

### Dashboard

```bash
cd dashboard
npm install

# Create .env.local
NEXT_PUBLIC_SUPABASE_URL=your-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-key

npm run dev        # localhost:3000
npm run build      # production build
```

Deploy to Vercel with `dashboard/` as root directory.

---

## Database

Create these tables in Supabase:

<details>
<summary><b>replied_tweets</b> — reply log with engagement tracking</summary>

```sql
CREATE TABLE replied_tweets (
  tweet_id TEXT PRIMARY KEY,
  reply_tweet_id TEXT,
  author_username TEXT NOT NULL,
  reply_text TEXT NOT NULL,
  tweet_url TEXT,
  keyword TEXT,
  score FLOAT DEFAULT 0,
  posted_at TIMESTAMPTZ DEFAULT now(),
  engagement_likes INT,
  engagement_impressions INT,
  engagement_checked TIMESTAMPTZ,
  reply_style TEXT,
  source_type TEXT DEFAULT 'keyword'
);
```
</details>

<details>
<summary><b>keyword_stats</b> — per-keyword performance</summary>

```sql
CREATE TABLE keyword_stats (
  keyword TEXT PRIMARY KEY,
  attempts INT DEFAULT 0,
  successes INT DEFAULT 0,
  total_likes INT DEFAULT 0,
  total_impressions INT DEFAULT 0,
  last_used TIMESTAMPTZ,
  last_success TIMESTAMPTZ
);
```
</details>

<details>
<summary><b>style_stats</b> — per-style performance</summary>

```sql
CREATE TABLE style_stats (
  style TEXT PRIMARY KEY,
  attempts INT DEFAULT 0,
  successes INT DEFAULT 0,
  total_likes INT DEFAULT 0,
  total_impressions INT DEFAULT 0,
  last_used TIMESTAMPTZ,
  last_success TIMESTAMPTZ
);
```
</details>

<details>
<summary><b>reply_reviews</b> — approval audit log</summary>

```sql
CREATE TABLE reply_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tweet_id TEXT NOT NULL,
  author_username TEXT,
  tweet_text TEXT,
  tweet_url TEXT,
  ai_reply_text TEXT NOT NULL,
  final_reply_text TEXT NOT NULL,
  outcome TEXT CHECK (outcome IN ('approved','edited','rejected','auto_approved')),
  reply_style TEXT,
  source_type TEXT,
  score FLOAT,
  keyword TEXT,
  reviewed_at TIMESTAMPTZ DEFAULT now(),
  response_time_seconds INT
);
```
</details>

---

## Configuration

Key tuning knobs in `tweetgod/config.py`:

| Setting | Default | Description |
|:---|:---:|:---|
| `daily_post_limit` | 12 | Max replies per day |
| `active_hour_start/end` | 8-23 ET | Bot active window |
| `schedule_interval_min/max` | 25-55 min | Randomized run interval |
| `max_tweet_age_hours` | 6 | Ignore tweets older than this |
| `top_n_candidates` | 5 | Tweets to pick from after scoring |
| `approval_timeout_minutes` | 15 | Telegram approval window |
| `priority_score_boost` | 1.20 | 20% score bump for whale accounts |
| `max_style_percentage` | 0.40 | Max 40% of daily replies in one style |
| `require_approval` | true | Telegram review before posting |

---

## Tech Stack

| Layer | Technology |
|:---|:---|
| **Bot** | Python 3.12, tweepy, httpx, APScheduler, Pydantic |
| **LLM** | xAI Grok (`grok-4-1-fast-non-reasoning`) |
| **Scraping** | Apify Twitter Scraper |
| **Dashboard** | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| **Database** | Supabase (PostgreSQL) |
| **Hosting** | Railway (bot) + Vercel (dashboard) |

---

<div align="center">

**Built by [Chase](https://x.com/ChaseAI)**

</div>
