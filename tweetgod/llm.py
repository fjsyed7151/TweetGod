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

Your job:
- Preserve his exact voice, ideas, and wording
- Only fix obvious typos and remove filler words
- Tighten phrasing slightly if needed
- Do NOT add ideas, change his stance, or make it sound more polished/corporate
- If it's already good, return it nearly unchanged

Voice rules (these are the user's actual style — match them, don't fight them):
- Tone: casual, like texting a friend who also invests. Sharp but not stiff.
- Lowercase by default. Only capitalize proper nouns and finance acronyms (DCF, FCF, ROIC, WACC, EBITDA, P/E, EV, Fed, SEC, etc.). When in doubt, lowercase.
- Sentences are usually short and direct.
- Use these contractions/shorthand if the raw input already does (don't add them where he didn't): "ye" (not "yea"/"yeah"), "u" (not "you"), "id" (not "I'd"/"I would"), "idk".
- Do NOT end a single-sentence tweet with a period. Multi-sentence tweets get normal punctuation.
- Almost never use emojis.
- No hashtags, no @mentions.
- Do NOT use em-dashes (— or –) or en-dashes.
- For publicly-traded companies you're confident about, use the ticker prefixed with $ (e.g. $TSLA, $AAPL, $MSFT). Prefer tickers over spelling out company names. Never put any character immediately to the left of $ — write "$TSLA" or " $TSLA", never "($TSLA)" or "/$TSLA". Only use $ if you're sure of the ticker.
- Avoid corporate/AI words like: delve, utilize, leverage, robust, pivotal, crucial, comprehensive, vital, notably, furthermore, moreover, additionally, indeed, showcasing, aligns, noteworthy, landscape, game-changer, navigate, realm, foster, streamline, innovative, cutting-edge, transformative, seamless, elevate, unlock, harness, empower, groundbreaking, revolutionary, synergy.

When the user prompt includes a "RELEVANT EXCERPTS FROM YOUR PUBLISHED WORK" section, treat those excerpts as factual sources you can draw on:
- Use them for specifics (numbers, definitions, frameworks, mechanics) to make the polished tweet sharper and more accurate. Don't fabricate details that aren't in the excerpts or the raw take.
- Only include an article URL if the link would genuinely help the reader. Most tweets should NOT include any link. If linking, paste the bare URL inline.
- Never say "I wrote about this", "check out my article", "in my piece on X", or anything similar — too promotional.
- Never link more than one article per tweet.
- Do NOT cite or reference the excerpts as sources in the tweet text — just use the knowledge naturally.

Respond with JSON only: {"polished": "the cleaned up text"}"""


async def polish_quote_tweet(raw_text: str, tweet: Tweet) -> str | None:
    """Polish Fajasy's raw input into a quote tweet.

    Returns the polished text string, or None on failure.
    """
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter analytics attribution (optional but recommended)
        "HTTP-Referer": "https://stablebread.com",
        "X-Title": "TweetGod (StableBread)",
    }

    user_prompt = (
        f"Clean up this raw take for a quote tweet (max 280 chars).\n\n"
        f"Original tweet by @{tweet.author_username}: \"{tweet.text[:300]}\"\n\n"
        f"Fajasy's raw take: \"{raw_text}\""
    )

    # RAG: pull relevant chunks from his published corpus, inject as context.
    # Off by default (RAG_ENABLED). Failures fall through silently — no excerpts
    # is always safer than a half-baked retrieval breaking the polish call.
    if settings.rag_enabled:
        try:
            from tweetgod.rag import retrieve_context, format_excerpts
            query = f"{tweet.text}\n\n{raw_text}"
            chunks = retrieve_context(query)
            if chunks:
                excerpts = format_excerpts(chunks)
                user_prompt += (
                    f"\n\nRELEVANT EXCERPTS FROM YOUR PUBLISHED WORK:\n\n"
                    f"{excerpts}"
                )
                log.info(
                    "RAG: injected %d excerpts (top similarity=%.3f)",
                    len(chunks),
                    chunks[0].get("similarity", 0.0),
                )
            else:
                log.info("RAG: no relevant chunks found for this candidate")
        except Exception:
            log.warning("RAG retrieval failed, polishing without context", exc_info=True)

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": POLISH_SYSTEM_PROMPT},
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
                log.warning("Polished text contains banned word '%s', returning raw input", word)
                return raw_text[:280]

        # Enforce 280 char limit
        if len(polished) > settings.max_quote_length:
            log.warning("Polished text too long (%d chars), truncating", len(polished))
            polished = polished[:settings.max_quote_length]

        if len(polished) < settings.min_quote_length:
            log.warning("Polished text too short (%d chars)", len(polished))
            return None

        return polished

    except Exception:
        log.error("LLM polish failed", exc_info=True)
        return None
