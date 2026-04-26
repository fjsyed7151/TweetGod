# TweetGod: Deep Dive Guide

**A masterclass on when to build an app vs. use Claude Code directly, why TweetGod was built the way it was, and how to set up your own version from scratch.**

---

## Table of Contents

1. The Decision Matrix: Claude Code vs. Building an App
2. Why TweetGod Was Built This Way
3. Architecture Breakdown
4. Step-by-Step Setup Guide

---

## Part 1: The Decision Matrix

### The Core Question

"Should I just use Claude Code for this, or should I build an actual application?"

This is the most common question I get, and the answer comes down to four factors. If your project hits **any** of these, you need an app. If it hits none, Claude Code alone is probably the right call.

### The Four Signals That Mean "Build an App"

#### 1. Does it need to run continuously or on a schedule?

Claude Code is a session. You open it, do work, close it. If your thing needs to run at 2 AM while you're asleep, or check something every 30 minutes, or stay alive indefinitely — that's an app. Claude Code can't be a daemon. It can't sit there running a scheduler 24/7.

**TweetGod example:** The bot runs every 25-55 minutes during active hours, checks engagement every 6 hours, and stays alive listening for Telegram commands around the clock. You can't prompt Claude Code to do that.

**Other examples:** A price drop monitor that checks Amazon every hour. A daily report generator that fires at 6 AM. A Slack bot that's always listening.

**Claude Code territory:** "Analyze this CSV and give me a summary." "Refactor this function." "Write tests for this module." All one-shot tasks with a clear start and end.

#### 2. Do other people need to use it?

Claude Code is single-player. You're the operator — you start sessions, you see results, you're the only one interacting with it. The moment someone else needs to interact with your thing — a client checking a dashboard, a teammate approving requests, a customer using a tool — you need a deployed app. There's no way to give someone else access to your Claude Code session.

**TweetGod example:** The analytics dashboard is a web app on Vercel that anyone with the URL can view. If you wanted a second person reviewing tweets or a client checking their engagement stats, that has to be a deployed web app.

**Other examples:** A client portal. A tool your team shares. Any product with users other than you.

**Claude Code territory:** Anything only you interact with — personal scripts, analysis, code generation, research. If you're the only user, Claude Code sessions might be enough.

#### 3. Does it need to respond to external events in real time?

Claude Code can call out to the world, but the world can't call in to Claude Code. If something external needs to trigger your system — a webhook fires, a user submits a form, a payment comes through, someone sends a Telegram message — something needs to be **listening right now** to catch that event the moment it happens. Claude Code isn't sitting there waiting for incoming requests.

**TweetGod example:** The Telegram listener polls every 3 seconds for your response. When you type "1" to approve a tweet, something has to be alive to receive that message immediately. That's a persistent process, not a Claude Code session.

**Other examples:** A Stripe webhook receiver that processes payments. A chatbot that responds to users in real time. A GitHub bot that comments on PRs when they're opened.

**Claude Code territory:** Calling APIs on your schedule — "fetch this data", "post this thing", "check this endpoint." Outbound calls are fine. It's inbound events that require an app.

#### 4. Does it need to maintain state across thousands of runs?

Claude Code has memory files, and they work for lightweight persistence. But if your system needs to track thousands of records, query historical data, or maintain complex relational state across months of operation — you need a real database, which means you need an app.

**TweetGod example:** The bot has replied to hundreds of tweets, tracked keyword performance across thousands of runs, and stored every approval decision with timestamps and response times. That's 4 Supabase tables with relational data. Memory files can't do that.

**Other examples:** A CRM tracking hundreds of leads and interactions. An analytics system aggregating months of data. Anything where you'd say "let me query the data from last month."

**Claude Code territory:** Remembering preferences, recent context, a short list of items. If your state fits in a markdown file, Claude Code memory is fine. If you need SQL queries, you need a database.

### The Hybrid Approach (What I Actually Do)

Here's what most people miss: **I used Claude Code to build TweetGod.** It's not either/or. The workflow is:

1. **Design with Claude Code** — Talk through the architecture, get the plan right
2. **Build with Claude Code** — Write every module, test, and config file
3. **Deploy the app** — Push to Railway/Vercel so it runs independently
4. **Iterate with Claude Code** — When I need changes, I open Claude Code and modify the codebase

Claude Code is the *builder*. The app is the *product*. You use one to create the other.

### Quick Reference

| Use Case | Claude Code | App | Why |
|:---|:---:|:---:|:---|
| One-time analysis or transformation | X | | One-shot, just you |
| Refactoring or code review | X | | One-shot, just you |
| Exploring or calling an API | X | | Outbound calls, no persistence needed |
| Writing a script you'll run once | X | | No schedule, no other users |
| Scheduled data processing | | X | Runs on a schedule without you |
| Monitoring + alerting | | X | Runs continuously, responds to events |
| Social media automation | | X | Scheduled, event-driven, needs state |
| Dashboard or client portal | | X | Other people need to access it |
| Chatbot or interactive tool | | X | Responds to external events in real time |
| Webhook receiver (Stripe, GitHub, etc.) | | X | World calls in — needs to be listening |
| CRM or data system with history | | X | Thousands of records, needs a real database |

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

The pipeline runs through these steps in order:

1. **Select Mode** — Priority accounts (55%), Trending (30%), Community (5%), or Keywords (10%)
2. **Scrape Tweets** — Apify fetches 40-90 tweets matching the search
3. **Filter** — Quality gates, deduplication, author diversity limits
4. **Score & Rank** — 5-signal composite score, top 5 pool
5. **Softmax Pick** — Probabilistic selection from the top 5
6. **Telegram Approval** — You type your take, Grok polishes, you approve
7. **Post & Track** — Quote tweet posted, saved to database, notification sent

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
| `poster.py` | Quote tweet posting via Typefully API | Thin wrapper around Typefully v2 |
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

This is inspired by the UCB1 (Upper Confidence Bound) multi-armed bandit algorithm. It balances:

- **Exploitation** — Use keywords that have historically performed well
- **Exploration** — Try under-used keywords in case they're secretly great

After posting a quote tweet, the system waits 20-28 hours then checks engagement via the Twitter API. If likes/impressions >= 0.5%, it's a success. The keyword stats get updated, and future runs favor keywords with higher success rates. Keywords with few attempts get an exploration bonus (they might be hidden gems). Recently used keywords get a small penalty to encourage variety.

### The Telegram Approval Flow

Here's what the actual flow looks like:

1. Bot finds a tweet opportunity and sends you a Telegram message with: author, follower count, tweet text, likes, RTs, age, score, source type, and a direct link to view the tweet
2. You type your raw take (stream of consciousness, typos and all) — or "5" to skip
3. Grok polishes your text (fixes typos, tightens phrasing, preserves your voice)
4. You see the polished version and choose: "1" to post, type edits for another pass, or "5" to skip
5. If approved, the quote tweet goes live and you get a confirmation with a link

---

## Part 4: Step-by-Step Setup Guide

### What You'll Need

- **Claude Code** (you already have this — it's going to do most of the heavy lifting)
- **Python 3.12+** installed on your machine
- **Node.js 18+** (only if you want the optional analytics dashboard)
- About 30-45 minutes for the initial setup
- Free accounts on 6 services: Twitter/X, Apify, xAI, Supabase, Telegram, and Railway

### Overview

Here's the game plan: you're going to clone a ready-to-go template repo, sign up for 6 services and grab your API keys, then tell Claude Code to wire everything together and customize it for your niche. You don't need to understand the code — Claude Code does. Your job is to get the API keys and tell Claude Code what niche you're in.

---

### Step 1: Clone the Repo and Open Claude Code

Open your terminal and run:

```bash
git clone https://github.com/cth9191/TweetGod-template.git
cd TweetGod-template
```

This gives you the full TweetGod codebase with placeholder config ready to customize. Now open Claude Code inside that directory:

```bash
claude
```

Claude Code is now your co-pilot for the rest of this setup. Keep it open — you'll be pasting API keys into it and asking it to configure things for you.

---

### Step 2: Sign Up for Your 6 Services

Before we configure anything, let's get all the API keys in one go. Open these in separate browser tabs and sign up for each one. You'll need a free account on all of them.

#### 2a. Twitter/X Developer Account

This gives you the API keys to read tweets and post quote tweets.

1. Go to **https://developer.x.com/en/portal/dashboard**
2. Sign up for a free developer account if you don't have one
3. Create a new Project and App
4. **Important:** Set your app permissions to **"Read and Write"** (not just Read — this is the #1 mistake people make)
5. Go to "Keys and Tokens" and generate all of these:
   - API Key
   - API Key Secret
   - Access Token
   - Access Token Secret
   - Bearer Token

Save all 5 values somewhere (a text file, notes app, whatever). You'll paste them into Claude Code in a minute.

**Free tier limits:** 500 posts/month (roughly 16/day). TweetGod defaults to 12/day to stay safely under this.

#### 2b. Apify (Tweet Scraping)

Apify is what actually searches Twitter for tweets. It handles rate limits and parsing so you don't have to.

1. Go to **https://console.apify.com/** and create an account
2. Go to Account → Integrations → API Tokens
3. Create a new token and save it

**Cost:** Free tier gives you some usage. For regular use, expect ~$5-10/month.

#### 2c. xAI / Grok (LLM for polishing tweets)

Grok takes your raw stream-of-consciousness take and cleans it up — fixes typos, tightens phrasing, keeps your voice. It doesn't write for you, it just polishes.

1. Go to **https://console.x.ai/**
2. Create an account and generate an API key
3. Save the key

**Cost:** Well under $1/month for tweet polishing.

#### 2d. Supabase (Database)

Supabase stores everything: which tweets you've replied to, how each keyword performs, your full approval history. It's also what the optional dashboard reads from.

1. Go to **https://supabase.com** and create a free account
2. Create a new project (pick any region close to you, set a database password)
3. Wait for it to provision (~30 seconds)
4. Now create the tables — go to **SQL Editor** in the left sidebar, click "New Query", open the `setup.sql` file from the repo you cloned, paste the entire contents, and click **Run**

Now grab your credentials:

1. Go to **Settings → API** in the left sidebar
2. Save the **Project URL** (looks like `https://abc123.supabase.co`)
3. Save the **service_role key** (under "Project API keys" — it's the longer one labeled "service_role", NOT the anon key)

**The service_role key has full database access. Never share it publicly or commit it to git.**

#### 2e. Telegram Bot (Approval Flow)

Telegram is how the bot talks to you. It sends you tweet opportunities on your phone, you type your take, and it posts after you approve.

**Create the bot:**

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "My TweetGod") and username (e.g., `my_tweetgod_bot`)
4. BotFather gives you a token — save it

**Get your chat ID:**

1. Send any message to your new bot (just say "hi")
2. Open this URL in your browser (replace YOUR_TOKEN with the actual token):
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
3. In the JSON response, find `"chat":{"id":123456789}` — that number is your chat ID. Save it.

#### 2f. Railway (Bot Hosting)

Railway is where your bot runs 24/7 in the cloud. You don't deploy yet — just create the account now so it's ready.

1. Go to **https://railway.app** and sign up (GitHub login is easiest)

**Cost:** $5/month Hobby plan. TweetGod uses ~$2-3/month in compute.

---

### Step 3: Give Claude Code Your API Keys

You should now have API keys/tokens from all 6 services saved somewhere. Time to wire them up. Go back to Claude Code (which should still be open in your TweetGod-template directory) and say:

> "Create a .env file from .env.example. Here are my values:"

Then paste in your keys:

```
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=x-ai/grok-4.1-fast
TYPEFULLY_API_KEY=your_typefully_key_here
TYPEFULLY_SOCIAL_SET_ID=
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
APIFY_API_TOKEN=your_apify_token_here
```

Claude Code will create the `.env` file with your values. This file is gitignored — it never gets committed or shared.

---

### Step 4: Tell Claude Code Your Niche

This is the fun part. The template has placeholder config — now you tell Claude Code who you are and what space you're in, and it fills everything in for you.

Say something like this to Claude Code:

> "I'm a [your role] in the [your niche] space. My Twitter handle is @[your handle]. Open config.py and do the following:
>
> 1. Update PERSONA with my name, bio, and how I write (I'm [casual/direct/technical/funny/etc])
> 2. Replace KEYWORDS with 20-30 search terms relevant to [your niche]
> 3. Replace PRIORITY_ACCOUNTS with the top 30-40 Twitter accounts in [your niche] — mix of big accounts (500K+), mid-tier builders (10K-100K), and official brand accounts
> 4. Replace TRENDING_KEYWORDS with 10-15 broad trending terms for [your niche]
> 5. Set my timezone to [your timezone]
> 6. Set active hours to [your preferred hours]"

**Example if you're a fitness coach:**

> "I'm a fitness coach and online trainer. My Twitter handle is @FitCoachMike. Open config.py and update PERSONA with my info — I write casually, very direct, no fluff. Replace KEYWORDS with fitness keywords like 'home workout', 'protein intake', 'progressive overload', 'creatine', 'calorie deficit', etc. Replace PRIORITY_ACCOUNTS with the top fitness Twitter accounts — Jeff Nippard, Dr. Mike Israetel, Layne Norton, Huberman, Athlean-X, etc. Set my timezone to US/Eastern and active hours to 7 AM - 9 PM."

Claude Code will rewrite the entire config for your niche. Review what it produces — if anything looks off, just tell it to adjust.

**Other settings worth reviewing:**

| Setting | Default | What to Consider |
|:---|:---:|:---|
| `daily_post_limit` | 12 | Twitter free tier allows ~16/day. Keep some buffer. |
| `active_hour_start` / `active_hour_end` | 10 / 18 | When YOUR audience is most active. |
| `timezone` | US/Central | Set to your timezone. |
| `approval_timeout_minutes` | 60 | How long the bot waits for you to respond before skipping. |
| `priority_account_chance` | 0.55 | How often the bot targets big accounts vs. searching keywords. |

---

### Step 5: Test It Locally

Before deploying to the cloud, let's make sure everything works. Tell Claude Code:

> "Install the Python dependencies and run a dry test of the bot."

Or if you prefer to do it yourself in the terminal:

```bash
pip install -r requirements.txt
python -m tweetgod.main --dry-run
```

This runs one pipeline cycle without actually posting anything. You should see:

- "TweetGod starting up"
- "Pipeline run: keyword=..."
- "Scraped X tweets"
- "Best tweet: @someone..."
- A Telegram message on your phone asking for your take

**If you get the Telegram message, everything is wired up correctly.** Type "5" to skip it (we're just testing).

If you get errors, just paste the error message into Claude Code:

> "I'm getting this error when running TweetGod: [paste the error]. Help me fix it."

**Common issues and what they mean:**

- **"Twitter API 403"** — Your app permissions are "Read" only. Go back to the Twitter developer portal, change to "Read and Write", and regenerate your access tokens.
- **"Apify error 401"** — Invalid API token. Double-check your APIFY_API_TOKEN in the .env file.
- **"Supabase relation does not exist"** — You forgot to run `setup.sql`. Go to Supabase SQL Editor and run it.
- **"Telegram sendMessage failed"** — Wrong bot token or chat ID. Verify both values.

---

### Step 6: Push to GitHub and Deploy to Railway

The bot works locally — now let's get it running 24/7 in the cloud. First, you need your own GitHub repo so Railway can deploy from it.

Tell Claude Code:

> "Create a new private GitHub repo called TweetGod under my account, set it as the remote origin, and push all the code."

Claude Code will handle the git setup. Once pushed, deploy to Railway:

1. Go to **https://railway.app** and log in
2. Click **"New Project"** → **"Deploy from GitHub Repo"**
3. Select your TweetGod repository
4. Railway sees the `Procfile` and automatically sets up a worker process

**Add your environment variables to Railway:**

1. Click on your service in Railway
2. Go to the **Variables** tab
3. Click **"Raw Editor"** and paste all your env vars (the same ones from your .env file, just the KEY=VALUE lines without comments)
4. Click "Update Variables"

**That's it.** Railway will build and deploy automatically. Within 25-55 minutes, you'll get your first Telegram notification with a tweet to quote. The bot is now running 24/7 — you can close your laptop.

**Monitoring:** Check the Railway **Logs** tab anytime to see your bot running. You'll see pipeline runs, scrape results, scores, and any errors in real time.

---

### Step 11 (Optional): Deploy the Analytics Dashboard

The dashboard gives you a web UI to see your posting history, keyword performance, and engagement trends.

1. Go to **https://vercel.com** and sign up (GitHub login)
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

**Want to change something?** Open Claude Code in your TweetGod directory and just describe what you want. For example:

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
