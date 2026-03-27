# TweetGod: Deep Dive Guide

**A masterclass on when to build an app vs. use Claude Code directly, why TweetGod was built the way it was, and how to set up your own version from scratch.**

By Chase (chaseai.io)

---

## Table of Contents

1. [The Decision Matrix: Claude Code vs. Building an App](#part-1-the-decision-matrix)
2. [Why TweetGod Was Built This Way](#part-2-why-tweetgod-was-built-this-way)
3. [Architecture Breakdown](#part-3-architecture-breakdown)
4. [Step-by-Step Setup Guide](#part-4-step-by-step-setup-guide)

---

## Part 1: The Decision Matrix

### The Core Question

"Should I just use Claude Code for this, or should I build an actual application?"

This is the most common question I get, and the answer comes down to four factors. If your project hits **any** of these, you need an app. If it hits none, Claude Code alone is probably the right call.

### The Four Signals That Mean "Build an App"

#### 1. Does it need to run continuously or on a schedule?

Claude Code is a session. You open it, do work, close it. If your thing needs to run at 2 AM while you're asleep, or check something every 30 minutes, or stay alive listening for events — that's an app.

**TweetGod example:** The bot runs every 25-55 minutes during active hours, checks engagement every 6 hours, and listens for Telegram commands 24/7. You can't prompt Claude Code to do that.

**Claude Code territory:** "Analyze this CSV and give me a summary." "Refactor this function." "Write tests for this module." All one-shot tasks with a clear start and end.

#### 2. Does it need to maintain state across sessions?

Claude Code's memory resets between conversations (aside from memory files, which are lightweight). If your system needs to remember what it's already done, track performance over time, or build up a dataset — you need a database, which means you need an app.

**TweetGod example:** The bot tracks every tweet it's replied to (deduplication), keyword performance over weeks (feedback loop), and engagement metrics (self-improvement). That's a Supabase database with 4 tables that persist across thousands of runs.

**Claude Code territory:** "Read this file and fix the bug." "What changed in the last 5 commits?" These don't need to remember anything between sessions.

#### 3. Does it integrate with multiple external APIs continuously?

Claude Code can make API calls in a single session, sure. But if your system needs to **continuously orchestrate** multiple services — scraping from one, processing with another, posting to a third, tracking with a fourth — that's app territory.

**TweetGod example:** Every single pipeline run touches 5 services: Apify (scraping), Supabase (database), xAI Grok (LLM polish), Telegram (approval), and Twitter (posting). These need to work together in a specific sequence, handle failures gracefully, and retry when things break.

**Claude Code territory:** "Call this API and format the response." One-off integrations or exploration.

#### 4. Does it involve a feedback loop?

If your system needs to learn from its own output — track what worked, adjust strategy, and improve over time — that's inherently stateful and continuous. App territory.

**TweetGod example:** Every 6 hours, the engagement tracker checks how posted tweets performed. Keywords that produce high-engagement replies get selected more often in future runs. The system literally gets smarter over time. You cannot build a self-improving loop in a Claude Code session.

**Claude Code territory:** "Analyze these results and suggest improvements." You can use Claude Code to *inform* your decisions, but the loop itself (act → measure → adjust → repeat) requires persistent infrastructure.

### The Decision Flowchart

```
Does it need to run on a schedule or continuously?
├── YES → Build an app
└── NO ─→ Does it need to remember things across sessions?
           ├── YES → Build an app
           └── NO ─→ Does it orchestrate multiple APIs continuously?
                      ├── YES → Build an app
                      └── NO ─→ Does it need to learn from its own output?
                                ├── YES → Build an app
                                └── NO ─→ Use Claude Code directly
```

### The Hybrid Approach (What I Actually Do)

Here's what most people miss: **I used Claude Code to build TweetGod.** It's not either/or. The workflow is:

1. **Design with Claude Code** — Talk through the architecture, get the plan right
2. **Build with Claude Code** — Write every module, test, and config file
3. **Deploy the app** — Push to Railway/Vercel so it runs independently
4. **Iterate with Claude Code** — When I need changes, I open Claude Code and modify the codebase

Claude Code is the *builder*. The app is the *product*. You use one to create the other.

### Quick Reference

| Use Case | Claude Code | App |
|:---|:---:|:---:|
| One-time analysis or transformation | X | |
| Refactoring or code review | X | |
| Exploring a new API | X | |
| Scheduled data processing | | X |
| Monitoring + alerting | | X |
| Social media automation | | X |
| Self-improving system | | X |
| Dashboard with live data | | X |
| Chatbot or interactive tool | | X |
| Writing a script you'll run once | X | |
| Writing a script you'll run daily | | X |

---

## Part 2: Why TweetGod Was Built This Way

### Why Quote Tweets Instead of Replies?

Early versions of TweetGod posted regular replies. The problem: replies are buried in threads. Quote tweets show up on *your* timeline, so your followers see them. They also show up as a notification for the original poster that carries more weight than a reply. Quote tweets are a growth mechanism; replies are engagement.

### Why Human-in-the-Loop Instead of Full Auto?

We tried fully automated replies first. The problem isn't quality — Grok can write decent tweets. The problem is **judgment**. The bot can't know:

- "This person is having a bad day, don't be contrarian here"
- "This is a sarcastic tweet, don't take it literally"
- "This is actually a dumb take, I shouldn't amplify it"
- "I actually disagree with the popular opinion here, let me say something real"

The current flow: the bot finds the opportunity, I provide my actual take (stream of consciousness, typos and all), Grok cleans it up, and I approve the final version. My voice, my judgment, AI efficiency. Best of both worlds.

### Why Grok Instead of Claude for the LLM?

Grok is used specifically for tweet polishing because:

1. **Speed** — `grok-4-1-fast-non-reasoning` is extremely fast, which matters when you're in a Telegram approval flow and waiting for the polish
2. **Twitter-native context** — Grok is trained on Twitter data and understands tweet conventions
3. **Cost** — The polishing task is simple (fix typos, tighten phrasing). Using a frontier model like Opus for this would be overkill

Claude is the better model for complex reasoning. But "clean up this 200-character tweet" isn't complex reasoning.

### Why Apify Instead of the Twitter API for Scraping?

Twitter's API (v2) is deliberately limited on the free tier. You get 500 posts/month for writing and very limited read access. Apify's tweet scraper handles:

- Search queries with boolean operators (`from:user1 OR from:user2`)
- Rate limit management
- Parsing inconsistent Twitter data formats
- Much higher volume than the official API allows

The tradeoff is cost (~$5-10/month on Apify) and slightly more latency. Worth it for the volume and flexibility.

### Why Supabase Instead of a Local Database?

Three reasons:

1. **Hosted** — No database to manage or back up. It just runs.
2. **Dashboard access** — The Next.js dashboard queries Supabase directly. No backend API needed.
3. **Free tier** — The free plan handles TweetGod's volume easily (hundreds of rows, not millions).

SQLite would have worked locally but wouldn't let the dashboard access data without building a separate API layer.

### Why Railway for the Bot?

The bot is a **long-running Python process**. It starts up, runs a scheduler, and stays alive indefinitely. This rules out serverless platforms:

- **Vercel** — Serverless. Functions timeout after 10-60 seconds. Can't run a persistent scheduler.
- **AWS Lambda** — Same problem. Max 15-minute execution. You'd need to architect around it with EventBridge + Step Functions. Way more complexity.
- **Heroku** — Would work but costs more than Railway and has a worse developer experience.
- **Railway** — $5/month, connects to your GitHub repo, auto-deploys on push, runs a persistent worker process. Perfect fit.

The key insight: **serverless is for request/response workloads. Long-running workers need a container platform.** Railway, Render, and Fly.io all work here. Vercel, Netlify, and Lambda don't.

### Why Vercel for the Dashboard?

The dashboard *is* a request/response workload. Someone loads a page, it queries Supabase, renders the data. That's exactly what Vercel is built for. It also has first-class Next.js support (they created it), free SSL, global CDN, and zero config deploys.

### Why Telegram for Approval Instead of a Web UI?

Speed. When a tweet opportunity comes in, I need to respond fast (the tweet is losing freshness every minute). Telegram gives me:

- Push notifications on my phone
- Instant response from anywhere
- Simple text interface (no buttons to click, no pages to load)
- Commands built in (`/pause`, `/resume`, `/status`)

A web dashboard would require me to have a browser open, watching for new opportunities. Telegram lets me respond from the gym, from a meeting, from bed.

### Why Randomized Intervals Instead of Fixed Schedule?

Two reasons:

1. **Anti-detection** — Twitter flags bot-like behavior. Posting at exactly 30-minute intervals is a signal. Random jitter between 25-55 minutes looks human.
2. **Natural distribution** — Real people don't tweet on a fixed schedule. The randomization creates a more natural posting pattern.

### Why Softmax Selection Instead of Always Picking the Best Tweet?

If you always pick the highest-scored tweet, you become predictable. You'd always reply to the biggest accounts, always chase the most viral tweets. Softmax with temperature 0.5 means:

- The best tweet gets picked *most* of the time
- But sometimes #2 or #3 gets picked
- This creates variety in your timeline
- You discover engagement opportunities you'd otherwise miss

It's the same explore/exploit tradeoff that makes the keyword selector work.

---

## Part 3: Architecture Breakdown

### The Pipeline (What Happens Every 25-55 Minutes)

```
                                    ┌──────────────────┐
                                    │  Select Mode     │
                                    │  Priority (55%)  │
                                    │  Trending (30%)  │
                                    │  Community (5%)  │
                                    │  Keyword (10%)   │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Scrape Tweets   │
                                    │  (Apify)         │
                                    │  40-90 tweets    │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Filter          │
                                    │  Quality gates   │
                                    │  Deduplication   │
                                    │  Author limits   │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Score & Rank    │
                                    │  5-signal score  │
                                    │  Top 5 pool      │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Softmax Pick    │
                                    │  Probabilistic   │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Telegram        │
                                    │  You type take   │
                                    │  Grok polishes   │
                                    │  You approve     │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │  Post & Track    │
                                    │  Quote tweet     │
                                    │  Save to DB      │
                                    │  Notify          │
                                    └──────────────────┘
```

### Module Map

| File | Purpose | Why It's Separate |
|:---|:---|:---|
| `main.py` | Pipeline orchestrator + scheduler | Entry point, coordinates everything |
| `config.py` | All settings, keywords, account lists | Single source of truth for tuning |
| `scraper.py` | Apify integration | Isolates the scraping API — easy to swap |
| `scorer.py` | 5-signal scoring algorithm | Pure math, no side effects, fully testable |
| `filters.py` | Quality gates (3 modes) | Business rules separated from scoring |
| `selector.py` | UCB1 keyword selection | Exploration/exploitation logic |
| `llm.py` | Grok polish integration | LLM calls isolated — swap models easily |
| `approval.py` | Telegram approval flow | Complex state machine, deserves its own file |
| `poster.py` | Twitter posting via tweepy | Thin wrapper around the Twitter API |
| `dedup.py` | Supabase read/write operations | All database logic in one place |
| `engagement_tracker.py` | 6-hour feedback loop | Checks past performance, updates stats |
| `notifier.py` | Telegram notifications | All outbound messages |
| `pause.py` | Pause/resume/status commands | Bot control flow |
| `models.py` | Pydantic data models | Shared types across all modules |

### The Scoring System

Each tweet gets a composite score from 5 weighted signals:

**Velocity (35-55%)** — How fast is this tweet gaining engagement? A tweet with 100 likes in 30 minutes is more valuable than 100 likes in 6 hours. Calculated as `(likes + retweets) / age_hours`, then log-scaled.

**Authority (20-30%)** — How many followers does the author have? Replies to big accounts get more visibility. Log10-scaled so it doesn't overwhelm other signals (1K followers = 3, 100K = 5, 1M = 6).

**Timing (10-20%)** — How fresh is the tweet? Exponential decay with a 2-hour half-life. A tweet posted 1 hour ago scores ~7. A tweet posted 4 hours ago scores ~2.5. You want to be early.

**Opportunity (5-10%)** — Reply gap. Tweets with lots of likes but few replies are underserved. Your reply has more room to be seen. High likes + low replies = high opportunity.

**Replyability (0-15%)** — Placeholder for LLM pre-screening. Not yet implemented — would rate how "reply-able" a tweet is before you spend time on it.

**Bonuses:**
- +30% for questions/discussion tweets (they invite replies)
- +25% for viral ratio (retweets/followers > 2.16)
- +20% for priority accounts

The weights shift based on mode. Trending mode cranks velocity to 55% because you're hunting virality. Standard mode is more balanced.

### The Feedback Loop

```
Post quote tweet
      │
      │  (wait 20-28 hours)
      │
      ▼
Check engagement via Twitter API
      │
      ├── likes / impressions >= 0.5%  →  SUCCESS
      │     Update keyword_stats: +1 success, +likes, +impressions
      │
      └── likes / impressions < 0.5%   →  Still tracked, just not a "success"

Future runs:
  Keywords with higher success rates → selected more often
  Keywords with low attempts → exploration bonus (might be hidden gems)
  Recently used keywords → small penalty (encourage variety)
```

This is inspired by the UCB1 (Upper Confidence Bound) multi-armed bandit algorithm. It balances:
- **Exploitation** — Use keywords that have historically performed well
- **Exploration** — Try under-used keywords in case they're secretly great

### The Telegram Approval Flow

```
Bot finds a tweet opportunity
      │
      ▼
Telegram message to you:
  "Quote Tweet Opportunity
   From: @karpathy (1.2M followers)
   'What's the best AI coding tool right now?'
   Likes: 2,340 | RTs: 89 | 1.2h ago
   Score: 7.82 | Source: priority
   [View Tweet]
   What's your take? (type your thoughts, or 5 to skip)"
      │
      ├── You type "5" → Skip, move on
      │
      └── You type "claude code obviously. nothing else comes close
          for real engineering work. the rest are toys"
            │
            ▼
      Grok polishes → "Claude Code, obviously. Nothing else comes close
                       for real engineering work. The rest are toys."
            │
            ▼
      Telegram: "Polished version:
                 'Claude Code, obviously. Nothing else comes close
                  for real engineering work. The rest are toys.'
                 1 to post | type edits | 5 to skip"
            │
            ├── You type "1" → Posts the quote tweet
            ├── You type "5" → Skip
            └── You type new text → Another polish cycle
```

---

## Part 4: Step-by-Step Setup Guide

### What You'll Need

- **Claude Code** (you already have this)
- **Python 3.12+** installed on your machine
- **Node.js 18+** (only if you want the analytics dashboard)
- About 30-45 minutes for the initial setup
- Accounts on: Twitter/X, Apify, xAI, Supabase, Telegram

### Overview

You'll be setting up 6 external services, then configuring and deploying the bot. Don't let the number of services intimidate you — each one takes about 5 minutes, and Claude Code will help you wire them together.

---

### Step 1: Clone the Repository

Open your terminal:

```bash
git clone https://github.com/cth9191/TweetGod.git
cd TweetGod
```

Then open Claude Code in that directory:

```bash
claude
```

---

### Step 2: Set Up Your Twitter/X Developer Account

This gives you the API keys to read and post tweets.

1. Go to https://developer.x.com/en/portal/dashboard
2. Sign up for a free developer account if you don't have one
3. Create a new Project and App
4. **Important:** Set your app permissions to **"Read and Write"** (not just Read)
5. Go to "Keys and Tokens" and generate:
   - API Key and Secret
   - Access Token and Secret
   - Bearer Token

Keep all 5 values somewhere safe — you'll need them in Step 7.

**Free tier limits:** 500 posts/month (roughly 16/day). TweetGod defaults to 12/day to stay safely under this.

---

### Step 3: Set Up Apify (Tweet Scraping)

Apify handles the heavy lifting of searching Twitter for tweets. Their scraper handles rate limits, parsing, and search operators.

1. Go to https://console.apify.com/ and create an account
2. Go to Account → Integrations → API Tokens
3. Create a new token and copy it

**Cost:** Apify has a free tier that gives you some usage. For regular use, expect ~$5-10/month depending on volume.

**Why Apify?** Twitter's official API heavily restricts search on the free tier. Apify's `apidojo~tweet-scraper` actor gives you much more flexibility — boolean search operators, higher volume, and consistent parsing.

---

### Step 4: Set Up xAI / Grok (LLM)

Grok polishes your raw thoughts into clean tweets. It doesn't generate content — it just cleans up typos and tightens your wording.

1. Go to https://console.x.ai/
2. Create an account and generate an API key
3. Copy the key

**Cost:** xAI pricing is usage-based. For tweet polishing (short inputs, short outputs), expect well under $1/month.

---

### Step 5: Set Up Supabase (Database)

Supabase is your database. It stores every tweet you've replied to, keyword performance stats, and the full approval audit log.

1. Go to https://supabase.com and create a free account
2. Create a new project (pick any region close to you, set a database password)
3. Wait for it to provision (~30 seconds)
4. Go to **SQL Editor** in the left sidebar
5. Click "New Query"
6. Open the `setup.sql` file from this repo and paste the entire contents
7. Click **Run** — this creates all 4 tables

Now get your credentials:
1. Go to **Settings → API** in the left sidebar
2. Copy the **Project URL** (looks like `https://abc123.supabase.co`)
3. Copy the **service_role key** (under "Project API keys" — it's the longer one labeled "service_role", NOT the anon key)

**The service_role key has full database access. Never expose it in frontend code or commit it to git.**

---

### Step 6: Set Up Telegram Bot (Approval Flow)

Telegram is how the bot communicates with you. It sends you tweet opportunities, you respond with your take, and it posts after you approve.

**Create the bot:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "My TweetGod") and username (e.g., `my_tweetgod_bot`)
4. BotFather gives you a token — copy it

**Get your chat ID:**
1. Send any message to your new bot (just say "hi")
2. Open this URL in your browser (replace YOUR_TOKEN with the actual token):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. In the JSON response, find `"chat":{"id":123456789}` — that number is your chat ID

---

### Step 7: Configure Environment Variables

Now wire everything together. In Claude Code, say:

> "Create a .env file from .env.example and I'll fill in my values"

Claude Code will create the file. Then fill in each value from the previous steps:

```
TWITTER_API_KEY=your_key_here
TWITTER_API_SECRET=your_secret_here
TWITTER_ACCESS_TOKEN=your_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_token_secret_here
TWITTER_BEARER_TOKEN=your_bearer_token_here
XAI_API_KEY=your_xai_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
APIFY_API_TOKEN=your_apify_token_here
```

---

### Step 8: Customize Your Configuration

This is where you make TweetGod yours. Open Claude Code and say:

> "Open config.py. I want to customize my persona, keywords, and priority accounts for my niche."

Here's what to change:

**PERSONA** (line ~101) — Change the name, bio, and voice description to match YOU. This is what Grok uses to understand your voice when polishing tweets.

**KEYWORDS** (line ~120) — These are the search terms the bot uses to find tweets. Replace them with keywords relevant to your niche. If you're in fitness, these might be "home workout", "protein intake", "progressive overload", etc.

**PRIORITY_ACCOUNTS** (line ~207) — These are the big accounts you want to quote-tweet. The bot checks their recent tweets 55% of the time. Pick 20-40 accounts in your space that have large, engaged audiences.

**TRENDING_KEYWORDS** (line ~156) — Broader terms for catching viral conversations. Keep these more general than your regular keywords.

**WATCHLIST_ACCOUNTS** and **WATCHLIST_KEYWORDS** (lines ~167, ~181) — Optional. Accounts you want instant alerts for when they tweet about specific topics. Remove these if you don't need them.

Tell Claude Code something like:

> "I'm a fitness coach. Update my PERSONA with my info, replace KEYWORDS with fitness/health keywords, replace PRIORITY_ACCOUNTS with the top fitness Twitter accounts, and update TRENDING_KEYWORDS for the fitness space."

Claude Code will rewrite all of these for you.

**Other settings to review:**

| Setting | Default | What to Consider |
|:---|:---:|:---|
| `daily_post_limit` | 12 | Twitter free tier allows ~16/day. Keep some buffer. |
| `active_hour_start` / `active_hour_end` | 10 / 18 | When YOUR audience is most active. |
| `timezone` | US/Central | Set to your timezone. |
| `approval_timeout_minutes` | 60 | How long the bot waits for you before skipping a tweet. |
| `priority_account_chance` | 0.55 | How often the bot targets big accounts vs. searching keywords. |

---

### Step 9: Install Dependencies and Test Locally

In your terminal (not Claude Code):

```bash
pip install -r requirements.txt
```

Then do a dry run to make sure everything connects:

```bash
python -m tweetgod.main --dry-run
```

This runs one pipeline cycle without actually posting anything. Watch the output — you should see:
- "TweetGod starting up"
- "Pipeline run: keyword=..."
- "Scraped X tweets"
- "Best tweet: @someone..."
- A Telegram message asking for your take

If you get errors, tell Claude Code:

> "I'm getting this error when running TweetGod: [paste the error]. Help me fix it."

Common issues:
- **"Twitter API 403"** — Your app permissions are set to "Read" only. Change to "Read and Write" in the developer portal, then regenerate your tokens.
- **"Apify error 401"** — Invalid API token. Double-check your APIFY_API_TOKEN.
- **"Supabase relation does not exist"** — You forgot to run `setup.sql`. Go to Supabase SQL Editor and run it.
- **"Telegram sendMessage failed"** — Wrong bot token or chat ID. Re-check both.

---

### Step 10: Deploy to Railway

Railway runs your bot 24/7 in the cloud so you don't need to keep your computer on.

1. Go to https://railway.app and sign up (GitHub login works)
2. Click **"New Project"** → **"Deploy from GitHub Repo"**
3. Select your TweetGod repository
4. Railway auto-detects the `Procfile` and sets up a worker

**Add your environment variables:**
1. Click on your service in Railway
2. Go to the **Variables** tab
3. Click **"Raw Editor"** and paste all your env vars in `KEY=VALUE` format (same as your .env file, minus the comments)

**That's it.** Railway will build and deploy automatically. You should start getting Telegram messages within the next pipeline cycle (25-55 minutes).

**Cost:** Railway's Hobby plan is $5/month with $5 of usage included. TweetGod typically uses $2-3/month in compute.

**Monitoring:** Check the Railway **Logs** tab to see your bot running. You'll see pipeline runs, scrape results, and any errors.

---

### Step 11 (Optional): Deploy the Analytics Dashboard

The dashboard gives you a web UI to see your posting history, keyword performance, and engagement trends.

1. Go to https://vercel.com and sign up (GitHub login)
2. Click **"Add New Project"** → import your TweetGod repo
3. Set the **Root Directory** to `dashboard`
4. Add these environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL` = your Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = your Supabase **anon** key (NOT the service_role key — the dashboard only needs read access, and this key is safe to expose in frontend code)
5. Deploy

Vercel will build the Next.js app and give you a URL. The dashboard has 5 tabs:
- **Overview** — Total replies, likes, best keyword
- **Replies** — Feed of all your quote tweets
- **Reviews** — Audit log (what you saw, what you typed, what happened)
- **Keywords** — Performance per keyword
- **Analytics** — 30-day trends

---

### Step 12: Daily Operations

Once deployed, here's your daily workflow:

**When a Telegram notification comes in:**
1. Read the tweet and the context (author, likes, age, score)
2. Click "View Tweet" to see it on Twitter if you need more context
3. Type your honest take — don't overthink it, stream of consciousness is fine
4. Review the polished version Grok sends back
5. Type "1" to post, type edits for another pass, or "5" to skip

**Telegram commands:**
- `/pause` — Pause the bot (default: 2 hours)
- `/pause 4h` — Pause for 4 hours
- `/pause today` — Pause until midnight
- `/resume` — Resume immediately
- `/status` — Check pause status + today's post count

**Tips for good results:**
- Be genuine. The best quote tweets add real value or a real perspective.
- Don't quote tweet just to agree. "Great point!" adds nothing.
- Controversial takes (when honest) perform best. Don't be contrarian for its own sake, but don't be afraid to disagree.
- Speed matters. Tweets lose value fast. Try to respond within a few minutes of getting the notification.
- Skip freely. If the tweet doesn't inspire a genuine reaction, skip it. Another one will come in 30 minutes.

---

### Troubleshooting

**Bot isn't sending Telegram messages:**
- Check Railway logs for errors
- Verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are correct
- Make sure you've messaged the bot at least once on Telegram

**Tweets aren't posting:**
- Check your Twitter app has "Read and Write" permissions
- Regenerate access tokens after changing permissions
- Check Railway logs for Twitter API errors

**"No tweets passed quality filter":**
- Your keywords might be too niche. Broaden them.
- Your priority accounts might not be tweeting during active hours. Add more accounts.
- The age filters might be too strict. In config.py, try increasing `max_tweet_age_hours`.

**Dashboard shows no data:**
- Make sure you're using the anon key (not service_role) for the dashboard
- Check that your Supabase URL is correct in Vercel env vars
- The bot needs to post at least one tweet before the dashboard has data to show

**Want to change something?**
Open Claude Code in your TweetGod directory and just describe what you want. For example:
- "Add a new keyword 'machine learning' to the keyword list"
- "Change active hours to 8 AM - 10 PM Eastern"
- "Add @elonmusk to my priority accounts"
- "Make the bot post up to 15 times per day instead of 12"

Claude Code can modify any part of the config or codebase for you.

---

### Cost Summary

| Service | Monthly Cost |
|:---|:---|
| Railway (bot hosting) | ~$5 |
| Apify (tweet scraping) | ~$5-10 |
| Supabase (database) | Free |
| Vercel (dashboard) | Free |
| xAI/Grok (LLM) | ~$1 |
| Twitter API | Free |
| Telegram | Free |
| **Total** | **~$11-16/month** |

---

### What's Next?

Once you have TweetGod running, here are things you can explore:

- **Tune your scoring weights** — If you're getting tweets that don't feel right, adjust the weights in `scorer.py`
- **Add more search modes** — The `selector.py` routing is easy to extend
- **Build a leaderboard** — Query `replied_tweets` to see which accounts you've engaged with most
- **A/B test approaches** — Track which types of quote tweets get the most engagement
- **Add auto-approval for certain accounts** — If you always approve quotes of @someone, automate that

All of these are things you can build by opening Claude Code and describing what you want. That's the power of having a well-structured codebase — Claude Code can navigate it and make precise changes.
