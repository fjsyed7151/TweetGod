"""Tweet quality filter.

Three-tier filtering:
  - Priority: dedup, language, text length, age, no-promo (skip engagement floors)
  - Trending: dedup, language, text length, age, min followers, velocity check
  - Keyword: adaptive thresholds with age adjustment (original behaviour)

Plus a topical relevance prefilter (non-priority modes only): tweets must
contain at least one finance/markets/investing signal AND must not be heavy
off-topic (politics, social causes, sports, generic promo). Priority accounts
bypass — they're curated by hand.
"""

from __future__ import annotations

import logging
import re

from tweetgod.config import settings
from tweetgod.models import Tweet

log = logging.getLogger(__name__)

# Promo patterns — reject tweets that are mostly promotional
_PROMO_PATTERNS = re.compile(
    r"\b(giveaway|contest|subscribe|retweet to win|drop your wallet|airdrop)\b",
    re.IGNORECASE,
)

# ── Topical relevance heuristics ──
# Positive: at least one of these must appear for a non-priority tweet to
# pass. Tickers ($AAPL etc.) count. Aim is to exclude obvious off-topic
# content that only matched a trending keyword incidentally.
_TICKER_RE = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")
_FINANCE_TERMS = re.compile(
    r"\b("
    # Securities & instruments
    r"stock|stocks|equity|equities|share|shares|bond|bonds|treasury|treasuries|"
    r"option|options|call|calls|put|puts|future|futures|warrant|warrants|"
    r"etf|etfs|reit|reits|fund|funds|hedge fund|"
    # Markets & indices
    r"market|markets|sector|index|indexes|indices|s&p|nasdaq|nyse|dow|russell|"
    r"bull|bear|bullish|bearish|rally|sell-?off|drawdown|correction|crash|"
    # Fundamentals & valuation
    r"earnings|revenue|profit|profits|loss|losses|margin|margins|guidance|"
    r"valuation|valuations|undervalued|overvalued|intrinsic|fair value|"
    r"dcf|ddm|fcf|free cash flow|owner earnings|"
    r"ebitda|ebit|roic|roce|roa|roe|eps|p/?e|pe ratio|ev|ev/?ebitda|"
    r"book value|tangible book|net income|operating income|cash flow|"
    r"income statement|balance sheet|wacc|capex|opex|"
    r"buyback|buybacks|repurchase|dilution|spin-?off|spinoff|split|"
    r"dividend|dividends|yield|yields|payout|"
    # Business analysis
    r"moat|competitive advantage|capital allocation|compounder|compounding|"
    r"earnings call|10-?k|10-?q|filing|sec filing|insider|"
    # M&A / events
    r"merger|acquisition|m&a|ipo|de-?spac|tender|buyout|"
    r"upgrade|downgrade|price target|analyst|analysts|consensus|"
    r"beat|missed|outlook|forecast|"
    # Macro
    r"recession|inflation|deflation|disinflation|stagflation|"
    r"fed|fomc|rate cut|rate hike|interest rate|interest rates|fed funds|"
    r"cpi|ppi|gdp|payrolls|nfp|jobs report|unemployment|"
    r"qe|qt|monetary policy|fiscal|deficit|debt ceiling|"
    # Investing strategy
    r"value investing|growth investing|quality|asymmetric|margin of safety|"
    r"portfolio|allocation|position|positions|long|short|hedge|"
    # Sectors / themes commonly traded
    r"semiconductor|semis|datacenter|cloud|saas|fintech|biotech|"
    r"oil|gas|crude|opec|gold|silver|commodities|"
    # Quick markers
    r"ticker|stock price|trading|trade idea|invest|investor|investors|investment"
    r")\b",
    re.IGNORECASE,
)

# Negative: tweets dominated by these are almost never what Fajasy would
# quote-tweet, even if they happen to mention an interest-rate-adjacent word.
_OFF_TOPIC_HEAVY = re.compile(
    r"\b("
    # US politics / social causes
    r"election|elections|vote|voted|voter|voting|ballot|candidate|congress|"
    r"senator|congressman|congresswoman|president biden|biden admin|"
    r"trump admin|kamala|harris admin|liberal|conservative|woke|cancel culture|"
    # Activism / cause language
    r"justice for|wrongfully|wrongful|exonerate|exonerated|innocent (?:baby|mother|man|woman|child)|"
    r"#justicefor|stand with|womens? rights|mens? rights|abortion|"
    r"gun control|immigration policy|"
    # Sports / entertainment
    r"nfl|nba|mlb|fifa|olympics?|world cup|super bowl|"
    r"taylor swift|kardashian|celebrity|tiktok dance|"
    # Crypto-pump / spam / promo
    r"airdrop|claim your|free mint|drop your wallet|whitelist|"
    r"engage with (?:them|us)|follow (?:this account|me back)|"
    r"appreciate my guy|much love|championing|"
    # Pure motivational fluff
    r"good morning everyone|happy (?:monday|tuesday|wednesday|thursday|friday)|"
    r"blessed|grateful|gn family"
    r")\b",
    re.IGNORECASE,
)

# Cleanup patterns for substantive-length check.
_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@\w+")
# Strip emoji + most non-BMP pictographs.
_EMOJI_RE = re.compile(
    "[\U00010000-\U0010ffff☀-➿⌀-⏿︀-️]",
    flags=re.UNICODE,
)
_WS_RE = re.compile(r"\s+")


def _substantive_length(text: str) -> int:
    """Length after stripping URLs, @mentions, emojis, whitespace runs.

    "The 🇺🇸 stock market just closed the day Red 🔻" → ~37 chars,
    versus raw len ~46. Catches short observations padded by emojis/flags.
    """
    cleaned = _URL_RE.sub("", text)
    cleaned = _MENTION_RE.sub("", cleaned)
    cleaned = _EMOJI_RE.sub("", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return len(cleaned)


def passes_topical_filter(tweet: Tweet, search_type: str) -> tuple[bool, str]:
    """Heuristic: is this tweet plausibly in Fajasy's niche?

    Returns (passes, reason). Reason is empty on pass, populated on reject.
    Priority searches bypass — the priority handles are curated.
    """
    if search_type == "priority":
        return True, ""

    text = tweet.text
    has_finance = bool(_TICKER_RE.search(text)) or bool(_FINANCE_TERMS.search(text))
    has_off_topic = bool(_OFF_TOPIC_HEAVY.search(text))

    # Hard reject: heavy off-topic with no countervailing finance content.
    if has_off_topic and not has_finance:
        return False, "off-topic (no finance signal)"

    # Soft reject: no finance signal at all.
    if not has_finance:
        return False, "no finance signal"

    return True, ""


def passes_quality_filter(
    tweet: Tweet,
    already_replied: set[str],
    search_type: str = "keyword",
) -> bool:
    """Return True if the tweet passes all quality checks."""
    reasons = []

    # ── Universal checks ──
    if tweet.tweet_id in already_replied:
        reasons.append("already replied")

    if tweet.language != "en":
        reasons.append(f"language={tweet.language}")

    if len(tweet.text) < settings.min_text_length:
        reasons.append(f"text too short ({len(tweet.text)} chars)")

    # ── Topical relevance heuristic (non-priority modes) ──
    # Catches the obvious off-topic stuff that leaks through trending /
    # keyword searches: political tweets, social-cause posts, "appreciate
    # my guy"-style promo, NFL hot takes, etc. Priority bypasses.
    topical_ok, topical_reason = passes_topical_filter(tweet, search_type)
    if not topical_ok:
        reasons.append(topical_reason)

    # ── Substantive-length check (non-priority modes) ──
    # Catches "🇺🇸 stock market closed Red 🔻" — finance term, short text,
    # nothing actually to react to. Priority sometimes posts brief takes
    # we still want to engage with.
    if search_type != "priority":
        sub_len = _substantive_length(tweet.text)
        if sub_len < settings.trending_min_substantive_length:
            reasons.append(f"low substance ({sub_len} substantive chars)")

    # ── Priority mode ──
    if search_type == "priority":
        if tweet.age_hours > settings.priority_max_age_hours:
            reasons.append(f"too old ({tweet.age_hours:.1f}h, max {settings.priority_max_age_hours}h)")

        if tweet.author_followers < settings.min_followers:
            reasons.append(f"followers={tweet.author_followers}")

        if _is_promo(tweet.text):
            reasons.append("promotional content")

    # ── Trending mode (velocity-based viral detection) ──
    elif search_type == "trending":
        if tweet.age_hours > settings.trending_max_age_hours:
            reasons.append(f"too old ({tweet.age_hours:.1f}h, max {settings.trending_max_age_hours}h)")

        if tweet.author_followers < settings.trending_min_followers:
            reasons.append(f"followers={tweet.author_followers} (need {settings.trending_min_followers})")

        # Velocity check: (likes + RTs) / age_hours
        age = max(tweet.age_hours, 0.1)
        velocity = (tweet.likes + tweet.retweets) / age
        if velocity < settings.trending_min_velocity:
            reasons.append(f"velocity={velocity:.1f}/hr (need {settings.trending_min_velocity})")

    # ── Keyword & community mode (original adaptive thresholds) ──
    else:
        if tweet.author_followers < settings.min_followers:
            reasons.append(f"followers={tweet.author_followers}")

        age = tweet.age_hours
        age_factor = _age_adjustment(age)

        adjusted_likes = settings.min_likes * age_factor
        adjusted_views = settings.min_views * age_factor
        adjusted_replies = settings.min_replies * age_factor

        if tweet.likes < adjusted_likes:
            reasons.append(f"likes={tweet.likes} (need {adjusted_likes:.0f})")

        if tweet.views < adjusted_views:
            reasons.append(f"views={tweet.views} (need {adjusted_views:.0f})")

        if tweet.replies < adjusted_replies:
            reasons.append(f"replies={tweet.replies} (need {adjusted_replies:.0f})")

        if age > settings.max_tweet_age_hours:
            reasons.append(f"too old ({age:.1f}h)")

    if reasons:
        log.debug("Filtered out @%s [%s]: %s", tweet.author_username, search_type, ", ".join(reasons))
        return False
    return True


def _is_promo(text: str) -> bool:
    """Detect promotional / link-heavy tweets."""
    # Check for promo keywords
    if _PROMO_PATTERNS.search(text):
        return True

    # Reject tweets that are mostly URLs (more than 40% of text is URLs)
    url_chars = sum(len(m) for m in re.findall(r"https?://\S+", text))
    if len(text) > 0 and url_chars / len(text) > 0.40:
        return True

    return False


def _age_adjustment(age_hours: float) -> float:
    """Lower the engagement threshold for very fresh tweets.

    < 1h  → 0.3x (a tweet only needs 30% of base thresholds)
    1-2h  → 0.5x
    2-4h  → 0.75x
    4-6h  → 1.0x (full thresholds apply)
    """
    if age_hours < 1:
        return 0.3
    elif age_hours < 2:
        return 0.5
    elif age_hours < 4:
        return 0.75
    else:
        return 1.0


def filter_tweets(
    tweets: list[Tweet],
    already_replied: set[str],
    search_type: str = "keyword",
) -> list[Tweet]:
    """Apply quality filter to a list of tweets."""
    passed = [t for t in tweets if passes_quality_filter(t, already_replied, search_type)]
    log.info("Quality filter [%s]: %d/%d tweets passed", search_type, len(passed), len(tweets))
    return passed


def apply_diversity_filter(tweets: list[Tweet], replied_authors_today: set[str]) -> list[Tweet]:
    """Remove tweets from authors we've already replied to today.

    Enforces max_replies_per_author_per_day = 1 by filtering out
    any tweet whose author is in the already-replied set.
    """
    filtered = [t for t in tweets if t.author_username not in replied_authors_today]
    removed = len(tweets) - len(filtered)
    if removed:
        log.info("Diversity filter: removed %d tweets from already-replied authors", removed)
    return filtered
