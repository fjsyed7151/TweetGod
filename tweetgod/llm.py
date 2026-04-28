"""LLM quote tweet polishing via OpenRouter (Grok 4.1 Fast).

Takes Fajasy's raw stream-of-consciousness input and lightly polishes it
into a quote tweet while preserving his voice.
"""

from __future__ import annotations

import json
import logging

import httpx

from tweetgod.config import settings
from tweetgod.models import Tweet

log = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

BANNED_WORDS = [
    "delve", "utilize", "leverage", "robust", "pivotal", "crucial",
    "comprehensive", "vital", "notably", "furthermore", "moreover",
    "additionally", "indeed", "showcasing", "aligns", "noteworthy",
    "landscape", "game-changer", "ever-evolving", "navigate", "realm",
    "foster", "streamline", "innovative", "cutting-edge", "embark",
    "intricacies", "transformative", "seamless", "elevate", "unlock",
    "unleash", "harness", "empower", "groundbreaking", "revolutionary",
    "synergy",
]

POLISH_SYSTEM_PROMPT = """You are cleaning up Fajasy's raw thoughts into a quote tweet. Fajasy is the founder of StableBread (stablebread.com), a value-investing education brand. Background: studied finance, then equity research, VC, startups, and consulting. Writes about stock analysis, stock valuation (DCF, DDM, multiples, comps), and portfolio management. 150+ articles, 500k+ words, cited by Investopedia, Goldman Sachs, OECD, Morningstar, KPMG, Chicago Booth. Audience is value investors from retail to professional, so finance lingo is welcome and expected.

YOUR JOB IS PRESERVATION, NOT REWRITING.
- Preserve his exact voice, ideas, and wording.
- Only fix obvious typos and remove filler words.
- Tighten phrasing slightly if a word is clearly junk.
- If the raw take is already 280 chars or under and reads cleanly, return it essentially as-is.
- Length should match the raw take's length. Short take = short polished. Don't pad.

ABSOLUTE BANS — if you violate any of these, you have failed:
- Do NOT echo, paraphrase, restate, or "build on" the original tweet being quoted. The quote tweet's whole job is to add HIS commentary, not summarize what's already visible right above it. If raw is "lol agreed", polished is "lol agreed" — NOT a recap of the original tweet.
- Do NOT add new ideas, claims, numbers, predictions, opinions, or reasoning he didn't write. If he wrote one sentence, you return one sentence's worth of his content. No expansion.
- Do NOT add contractions ("u", "ye", "id", "idk") if the raw take didn't already use them. If he wrote "you", keep "you". If he wrote "I would", keep "I would". Match what he typed.
- Do NOT add a link unless he explicitly asked for one OR his raw take is clearly pointing readers to deeper content. Default is no link. (See LINKING POLICY below.)
- Do NOT add disclaimers, hedges, or "this is not advice" type wrappers.

VOICE RULES (these describe HIS natural style — match what's already there, don't impose them):
- Tone: casual, like texting a friend who also invests. Sharp but not stiff.
- Lowercase by default. Only capitalize proper nouns and finance acronyms (DCF, FCF, ROIC, WACC, EBITDA, P/E, EV, Fed, SEC, etc.). If he typed mid-sentence capitals on regular words, lowercase them.
- Sentences are usually short and direct.
- Do NOT end a single-sentence tweet with a period. Multi-sentence tweets get normal punctuation.
- Almost never use emojis. If raw has none, polished has none.
- No hashtags, no @mentions.
- Do NOT use em-dashes (— or –) or en-dashes.
- For publicly-traded companies, use the ticker prefixed with $ (e.g. $TSLA, $AAPL, $MSFT) when you're sure of the ticker. Never put any character immediately to the left of $ — write "$TSLA" or " $TSLA", never "($TSLA)" or "/$TSLA".
- Avoid corporate/AI words like: delve, utilize, leverage, robust, pivotal, crucial, comprehensive, vital, notably, furthermore, moreover, additionally, indeed, showcasing, aligns, noteworthy, landscape, game-changer, navigate, realm, foster, streamline, innovative, cutting-edge, transformative, seamless, elevate, unlock, harness, empower, groundbreaking, revolutionary, synergy.

RAG EXCERPTS (when present): the user prompt may include a "RELEVANT EXCERPTS FROM YOUR PUBLISHED WORK" section.
- Use those ONLY to verify a number/term/spelling he already mentioned, or to pick the right ticker.
- Do NOT use them to add new content, sentences, or claims he didn't write.
- Do NOT cite or reference them in the tweet body.

LINKING POLICY (default = NO LINK):
- Only include a URL when (a) the raw take itself signals a link (e.g., "wrote about this", "deeper dive here", "more on this"), OR (b) one of the RAG excerpts is a near-perfect match for the SAME niche topic the take is making AND a curious reader would clearly benefit from clicking through. If the connection is loose or the tweet stands on its own, NO link.
- Maximum ONE URL per tweet, ever.
- When you do add a link, use his natural casual phrasing. Examples (vary them, don't copy verbatim):
    "i wrote about it here if interested: <url>"
    "got a deeper write-up here: <url>"
    "more on this here: <url>"
    "deeper dive here if u want: <url>"
- Do NOT use stiff/promotional phrasing like "Check out my article", "Read my comprehensive guide", "I authored", "in my piece on X".
- Use the bare URL — X auto-links it.

Respond with JSON only: {"polished": "the cleaned up text"}"""

ITERATE_SYSTEM_PROMPT = """You are revising a draft quote tweet for Fajasy based on his feedback. Fajasy is the founder of StableBread, a value-investing education brand. Audience is value investors. Finance lingo is welcome and expected.

YOU ARE REVISING. NOT POLISHING FROM SCRATCH. NOT ECHOING FEEDBACK.

The user prompt will give you:
- ORIGINAL TWEET — the tweet being quoted (for context only, do NOT echo or paraphrase it).
- RAW TAKE — Fajasy's original raw thought (his actual idea/stance — preserve this).
- PREVIOUS DRAFT — the polished version you previously produced.
- FEEDBACK — what Fajasy wants changed.

Your job:
- Apply the feedback to PREVIOUS DRAFT to produce a NEW polished draft.
- The output is the new draft only — never quote, restate, or include the feedback text itself.
- Preserve Fajasy's stance and ideas from RAW TAKE. Don't change his opinion to suit the feedback unless the feedback explicitly says so.
- If feedback is vague ("try again", "do it different", "no"), produce a meaningfully different rewrite of PREVIOUS DRAFT — different phrasing, different angle, same underlying take. Do NOT just resubmit the previous draft and do NOT include the feedback text.
- If feedback is specific ("make it shorter", "drop the link", "use $SNAP not Snap", "less hedging"), apply it precisely.
- Output length should be similar to PREVIOUS DRAFT unless feedback explicitly asks for shorter/longer.

ABSOLUTE BANS (same as polish):
- Do NOT echo or paraphrase the original tweet being quoted.
- Do NOT include the FEEDBACK text in the output. Ever.
- Do NOT add new ideas, claims, or numbers Fajasy didn't write.
- Do NOT add contractions ("u", "ye", "id", "idk") if RAW TAKE didn't use them.
- Do NOT add a link unless RAW TAKE asked for one or PREVIOUS DRAFT had one and feedback didn't say to drop it.

VOICE: casual, lowercase by default, no em-dashes, no hashtags/@mentions, no emojis (unless raw had them), no period on single-sentence tweets, $TICKER format for stocks, no corporate AI words (delve, utilize, leverage, robust, pivotal, comprehensive, etc.).

Respond with JSON only: {"polished": "the new revised draft"}"""

RELEVANCE_SYSTEM_PROMPT = """You screen tweets for Fajasy, founder of StableBread (stablebread.com), a value-investing education brand. He writes about stock analysis, valuation (DCF, DDM, multiples, comps, NAV), portfolio management, and capital markets. Audience: value investors, retail through professional. He has 150+ articles spanning fundamental analysis, financial statements, ratios, accounting quality, sector deep-dives, and macro context.

Your job: rate whether Fajasy could write a meaningful, on-brand QUOTE TWEET in response to this tweet. Score 0-10 strictly:

10 = directly about a specific stock, valuation, earnings, business model, capital allocation, accounting nuance, or investing thesis. Plenty to react to with a real take.
8-9 = clearly finance/markets — sector trend, macro print, Fed/rates take, M&A, bond market, credit, well-known investor framework.
6-7 = finance-adjacent with substance: business strategy, broad market commentary, earnings season vibes.
4-5 = mentions finance terms but is mostly vague / a brief observation / "market closed red"-tier.
2-3 = tangentially mentions money or business but is really about something else.
0-1 = off-topic for value investing entirely (politics, social causes, sports, gossip, generic motivation, crypto pumps, giveaways, "appreciate my guy" promo, justice campaigns, brief cheering observations, spam).

Bias toward LOW scores. If it's a one-liner with nothing meaningful to add to, it's a 4 at best — even if it mentions "stock market". The bar is "could he write something genuinely useful in response, or would the quote tweet be filler?"

Return JSON only: {"score": <integer 0-10>, "reason": "<6-12 word phrase explaining the score>"}"""


async def score_relevance(tweet: Tweet) -> tuple[int, str]:
    """LLM-rate how quote-tweetable this is for Fajasy. Returns (score 0-10, reason).

    Defaults to (5, "scoring failed") on error so failures don't auto-reject —
    the heuristic prefilter and human approval still gate everything.
    """
    user_prompt = (
        f"Tweet by @{tweet.author_username} ({tweet.author_followers:,} followers):\n"
        f"\"{tweet.text[:500]}\"\n\n"
        f"Score this tweet's quote-tweet relevance for Fajasy (StableBread)."
    )

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://stablebread.com",
        "X-Title": "TweetGod (StableBread) — relevance",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 80,
        "response_format": {"type": "json_object"},
        "reasoning": {"enabled": False},
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        score_raw = parsed.get("score", 5)
        try:
            score = max(0, min(10, int(score_raw)))
        except (TypeError, ValueError):
            score = 5
        reason = str(parsed.get("reason", "")).strip()[:120] or "no reason"
        return score, reason
    except Exception:
        log.warning("Relevance scoring failed for @%s", tweet.author_username, exc_info=True)
        return 5, "scoring failed"


def _build_rag_excerpts(query: str) -> str:
    """Pull relevant chunks from the corpus and format as excerpt block.

    Returns "" if RAG disabled, no hits, or any failure. Never raises.
    """
    if not settings.rag_enabled:
        return ""
    try:
        from tweetgod.rag import retrieve_context, format_excerpts
        chunks = retrieve_context(query)
        if not chunks:
            log.info("RAG: no relevant chunks found for this candidate")
            return ""
        log.info(
            "RAG: injected %d excerpts (top similarity=%.3f)",
            len(chunks),
            chunks[0].get("similarity", 0.0),
        )
        return (
            "\n\nRELEVANT EXCERPTS FROM YOUR PUBLISHED WORK:\n\n"
            + format_excerpts(chunks)
        )
    except Exception:
        log.warning("RAG retrieval failed, continuing without context", exc_info=True)
        return ""


async def _call_openrouter(system_prompt: str, user_prompt: str) -> str | None:
    """Call OpenRouter, parse the JSON response, return the polished string.

    Centralizes the HTTP call, banned-word check, em-dash strip, and length
    bounds so polish + iterate behave identically.
    """
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter analytics attribution (optional but recommended)
        "HTTP-Referer": "https://stablebread.com",
        "X-Title": "TweetGod (StableBread)",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        # Disable reasoning to match xAI's `grok-4-1-fast-non-reasoning` variant
        "reasoning": {"enabled": False},
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        polished = parsed.get("polished", "").strip()
        if not polished:
            log.warning("LLM returned empty polished text")
            return None

        # Strip em-dashes (AI giveaway)
        polished = polished.replace(" — ", ". ").replace("—", ". ")
        polished = polished.replace(" – ", ". ").replace("–", ". ")

        # Check for banned words
        lower = polished.lower()
        for word in BANNED_WORDS:
            if word in lower:
                log.warning("Polished text contains banned word '%s'", word)
                return None

        # Enforce 280 char limit
        if len(polished) > settings.max_quote_length:
            log.warning("Polished text too long (%d chars), truncating", len(polished))
            polished = polished[:settings.max_quote_length]

        if len(polished) < settings.min_quote_length:
            log.warning("Polished text too short (%d chars)", len(polished))
            return None

        return polished

    except Exception:
        log.error("LLM call failed", exc_info=True)
        return None


async def polish_quote_tweet(raw_text: str, tweet: Tweet) -> str | None:
    """Polish Fajasy's raw input into a quote tweet.

    Returns the polished text string, or None on failure.
    """
    user_prompt = (
        f"Clean up this raw take for a quote tweet (max 280 chars).\n\n"
        f"ORIGINAL TWEET (for context only — do NOT echo, paraphrase, or summarize this) by @{tweet.author_username}:\n"
        f"\"{tweet.text[:300]}\"\n\n"
        f"FAJASY'S RAW TAKE (preserve this — clean up only):\n"
        f"\"{raw_text}\""
    )
    user_prompt += _build_rag_excerpts(f"{tweet.text}\n\n{raw_text}")

    polished = await _call_openrouter(POLISH_SYSTEM_PROMPT, user_prompt)
    if polished is None:
        # Last-resort: return the raw text trimmed to 280, so the user still
        # has *something* to approve/edit rather than a hard fail.
        return raw_text[:settings.max_quote_length] if raw_text.strip() else None
    return polished


async def iterate_quote_tweet(
    raw_take: str,
    previous_draft: str,
    feedback: str,
    tweet: Tweet,
) -> str | None:
    """Revise an existing draft based on user feedback.

    Sends the LLM the original tweet, the raw take, the previous draft, AND
    the feedback as four separate fields — so the model knows to apply the
    feedback rather than treat it as new content to polish.

    Returns the new draft, or None on failure.
    """
    user_prompt = (
        f"Revise the previous draft based on Fajasy's feedback. Output ONLY "
        f"the new draft (max 280 chars). Do NOT include the feedback text in "
        f"your output.\n\n"
        f"ORIGINAL TWEET (context only — do NOT echo or paraphrase) by @{tweet.author_username}:\n"
        f"\"{tweet.text[:300]}\"\n\n"
        f"RAW TAKE (Fajasy's underlying idea — preserve his stance):\n"
        f"\"{raw_take}\"\n\n"
        f"PREVIOUS DRAFT (what you wrote last time):\n"
        f"\"{previous_draft}\"\n\n"
        f"FEEDBACK (what Fajasy wants changed):\n"
        f"\"{feedback}\""
    )
    user_prompt += _build_rag_excerpts(f"{tweet.text}\n\n{raw_take}\n\n{feedback}")

    new_draft = await _call_openrouter(ITERATE_SYSTEM_PROMPT, user_prompt)
    if new_draft is None:
        # Don't fall back to anything containing the feedback — better to return
        # the previous draft unchanged than to leak feedback into the tweet.
        log.warning("Iteration failed, returning previous draft unchanged")
        return previous_draft
    return new_draft
