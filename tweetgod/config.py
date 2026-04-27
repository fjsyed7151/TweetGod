from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    # OpenRouter (LLM polishing — replaces direct xAI Grok)
    openrouter_api_key: str = ""
    # Maps to xAI's `grok-4-1-fast-non-reasoning`. Reasoning is disabled
    # at the request layer in llm.py via {"reasoning": {"enabled": false}}.
    openrouter_model: str = "x-ai/grok-4.1-fast"

    # Typefully (posting + analytics — replaces direct Twitter API)
    typefully_api_key: str = ""
    # Optional: pin a specific social set. If empty, poster.py auto-discovers
    # the first social set with X enabled and caches it for the process.
    typefully_social_set_id: str = ""

    # OpenAI (RAG embeddings only — Grok still does the polish)
    openai_api_key: str = ""
    # text-embedding-3-large with dimensions=1536: best quality, fits HNSW
    openai_embed_model: str = "text-embedding-3-large"
    rag_enabled: bool = False  # flip to True in env after corpus is ingested

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
# Used by the LLM to understand voice when polishing quote tweets.

PERSONA = {
    "name": "Fajasy",
    "bio": (
        "Founder of StableBread (stablebread.com). Studied finance, then equity "
        "research, VC, startups, and consulting. Value investor focused on "
        "high-quality undervalued businesses for long-term returns. Writes about "
        "stock analysis, stock valuation (DCF, DDM, multiples, comps), and "
        "portfolio management. 150+ articles, 500k+ words, cited by Investopedia, "
        "Goldman Sachs, OECD, Morningstar, KPMG, Chicago Booth, and others. "
        "Builds spreadsheet models including an automated stock analysis sheet, "
        "financial/SEC metrics databases, and runs DCF/DDM courses."
    ),
    "voice": (
        "Casual, like texting a friend who also invests, but keeps real finance "
        "lingo since the audience is value investors. Lowercase by default; only "
        "proper nouns and finance acronyms (DCF, FCF, ROIC, WACC, EBITDA, P/E, "
        "Fed, SEC) get capitalized. Sentences usually short. No period at the "
        "end of single-sentence posts. Uses 'ye', 'u', 'id', 'idk' naturally. "
        "Almost never emojis. Uses $TICKER for public companies (no parentheses, "
        "no characters immediately left of the $). Avoids corporate/AI filler "
        "words and em-dashes."
    ),
}


# ── Keywords & Communities ───────────────────────────────────────────────────
# Search terms the bot uses to find tweets worth quote-tweeting.
# Targeted at value investing / fundamental analysis discourse.

KEYWORDS: list[str] = [
    # Valuation methods and inputs
    "DCF model",
    "intrinsic value",
    "free cash flow",
    "owner earnings",
    "discount rate",
    "WACC",
    "dividend discount model",
    "margin of safety",
    "stock valuation",
    "earnings quality",
    # Quality / business analysis
    "ROIC",
    "moat",
    "competitive advantage",
    "capital allocation",
    "earnings call",
    # Portfolio / strategy
    "value investing",
    "asymmetric bet",
    "portfolio construction",
    "position sizing",
]

TRENDING_KEYWORDS: list[str] = [
    # Broader market terms for catching viral conversations.
    "stock market",
    "earnings report",
    "Fed",
    "interest rates",
    "S&P 500",
    "recession",
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
# Value-investing accounts Fajasy already engages with.
# Bot samples `priority_sample_size` of these per run, 55% of the time.

PRIORITY_ACCOUNTS: list[str] = [
    "AltaFoxCapital", "HaydenCapital", "yliownyc", "FromValue",
    "benjaminfelix", "AndrewRangeley", "MohnishPabrai", "AswathDamodaran",
    "RamBhupatiraju", "jsblokland", "ballmatthew", "chriswmayer",
    "FocusedCompound", "aaronvalue", "borrowed_ideas", "mastersinvest",
    "10kdiver", "morganhousel", "mjmauboussin", "johnauthers",
    "larryswedroe", "safalniveshak", "TheRoaringKitty", "saxena_puru",
    "yesandnotyes", "LennyIce", "schaudenfraud", "TSOH_Investing",
    "MoatsLikeKodak", "ShortSightedCap", "NoonSixCap", "Ren_aramb",
    "MSmicrocaps", "MoneEchevarria", "Secrets4Stocks", "MediaKing",
    "thegresearch", "SteveDJacobs", "manualofideas", "usppdd",
    "pennycheck", "MoodyWriter13", "VladBastion", "rich_toad",
    "OptimizedPort", "MikeFritzell", "Scifospace", "BaselineByAS",
    "MoneyMarkStocks", "vjncapital_com", "DGretta_Author", "spacanpariman",
    "daniel_koss", "crux_capital_", "accounting_ds", "AlmostMongolian",
    "TheLAPurchaser", "CompoundingLab", "SpecialSitsNews", "AuditTheHerd",
    "GrumpierBTDay", "FundaAI", "Davey_juice", "GnDsville",
    "JohnTinsman", "Pixelresearch_", "rystivest", "8valueactivist",
    "TheStockSurgeon", "fincopilot", "TheStockerMan", "PolarizingLit",
    "varuninvesting", "Szew_invest", "EPSMonitor", "aijoin",
    "GuastyWinds", "fpcapital_", "BramVGenechten", "DrewCohenMoney",
    "Fred_Abyss", "RichardWedekin1", "bogumil_nyc", "walter_schloss",
    "LockStockBarrl", "Stocks_Stones", "MOS_Investing", "michaeljburry",
    "pattufreefincal", "sarfatti_IR", "HewittHeiserman", "MichaelBurry_",
    "MarioGabelli", "TheStocksKing", "MichaelZero10", "stepnotonpets",
    "joshtarasoff", "Kaizen_Investor", "romanchernin", "RobertJShiller",
    "DeutscheBank", "Fenmagne", "andrewcoye", "ValueInvestShow",
    "ReturnsJourney", "yianisz", "CJ0pp3l", "FeatherFund",
    "BoxLongs", "athcapitalmgtm", "IntrinsicInv", "KabraxFX",
    "aleabitoreddit", "PronkDaniel", "wisesheets", "Sandeman52",
    "orrdavid", "geokoutalidis", "Atrium_Research", "SimeonResearch_",
    "TherealDTMS", "RMantri", "mkfilko", "DeepValueBagger",
    "Gavekal", "GfI_Himmelreich", "TradeSignalHQ", "onecentnvest",
    "GilesCapital", "qualtrim", "ArthurCahuantzi", "Quant_Morales",
    "atomicalcapital", "yuvataylor", "ETMONEY", "EugeneNg",
    "Next100Baggers", "Speedwell_LLC", "TheOwnersEquity", "dede_eyesan",
    "themathharbaugh", "LeStonkJames", "rrvest091", "carbonfinancex",
    "P123Finance", "EightTrack180", "MindsetMoney_X", "jdmarkman",
    "RankEquity", "DurableCreators", "meetblossomapp", "theb1gideas",
    "MicroCapClub", "amitisinvesting", "MikeDDKing", "majgoeinvesting",
    "SebKrog", "SFarringtonBKC", "GabGrowth", "HenryChien4",
    "djpinvest", "IggyOnInvesting", "leevalueroach", "jasonzweigwsj",
    "vitaliyk", "KmateoK", "simpleinvest01", "DavidFool",
    "WOLF_Financial", "pernasresearch", "TacticzH", "Typhoon_Girl",
    "KobeissiLetter", "Oaktree", "CCVisuals", "finance_schmidt",
    "dsmoek98", "mvcinvesting", "ToffCap", "PrestonPysh",
    "valuewalk", "BrianFeroldi", "iancassel", "Greenbackd",
    "7LukeHallard", "F_Compounders", "PurdyInvestor", "MarketMaverickX",
    "Vivek_Investor",
]
