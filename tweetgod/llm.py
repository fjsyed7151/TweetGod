"""LLM quote tweet polishing via xAI Grok API.

Takes Chase's raw stream-of-consciousness input and lightly polishes it
into a quote tweet while preserving his voice.
"""

from __future__ import annotations

import json
import logging

import httpx

from tweetgod.config import settings
from tweetgod.models import Tweet

log = logging.getLogger(__name__)

GROK_API_URL = "https://api.x.ai/v1/chat/completions"

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

POLISH_SYSTEM_PROMPT = """You are cleaning up Chase's raw thoughts into a quote tweet. Chase is an AI consultant with an MBA and MS in Computer Science from UChicago. He runs Chase AI (chaseai.io) and is deep in the AI coding tools space.

Your job:
- Preserve his exact voice, ideas, and wording
- Only fix obvious typos and remove filler words
- Tighten phrasing slightly if needed
- Do NOT add ideas, change his stance, or make it sound more polished/corporate
- Keep his casual tone — lowercase is fine, fragments are fine
- If it's already good, return it nearly unchanged
- No hashtags, no @mentions
- Do NOT use em-dashes (— or –)

Respond with JSON only: {"polished": "the cleaned up text"}"""


async def polish_quote_tweet(raw_text: str, tweet: Tweet) -> str | None:
    """Polish Chase's raw input into a quote tweet.

    Returns the polished text string, or None on failure.
    """
    headers = {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }

    user_prompt = (
        f"Clean up this raw take for a quote tweet (max 280 chars).\n\n"
        f"Original tweet by @{tweet.author_username}: \"{tweet.text[:300]}\"\n\n"
        f"Chase's raw take: \"{raw_text}\""
    )

    payload = {
        "model": settings.xai_model,
        "messages": [
            {"role": "system", "content": POLISH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROK_API_URL, json=payload, headers=headers)
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
