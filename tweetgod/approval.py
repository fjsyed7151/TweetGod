"""Telegram approval flow for human-driven quote tweets.

Flow:
1. Present tweet to the user via Telegram
2. User types raw take (or "5" to skip)
3. LLM polishes the raw text
4. User approves ("1"), provides edits, or skips ("5")
5. Iterate until approved or skipped
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from pydantic import BaseModel

from tweetgod.config import settings
from tweetgod.models import ScoredTweet
from tweetgod.llm import polish_quote_tweet
from tweetgod.pause import parse_pause_command, pause_for, pause_until_tomorrow, resume

log = logging.getLogger(__name__)

# Flag so the background command listener knows to back off during approval
approval_active = False


class ApprovalResult(BaseModel):
    outcome: str  # "approved" | "edited" | "rejected" | "timeout"
    final_text: str
    raw_input: str = ""
    response_time_seconds: int | None = None


def _format_followers(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _build_tweet_message(
    candidate: ScoredTweet,
    keyword: str,
    score: float,
    search_type: str,
) -> str:
    """Build the initial tweet presentation message."""
    followers = _format_followers(candidate.tweet.author_followers)
    tweet_text = candidate.tweet.text
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."

    tweet_link = candidate.tweet.url or f"https://x.com/{candidate.tweet.author_username}/status/{candidate.tweet.tweet_id}"

    likes = candidate.tweet.likes
    rts = candidate.tweet.retweets
    age = candidate.tweet.age_hours

    username = candidate.tweet.author_username
    return (
        f"\U0001f4ac <b>Quote Tweet Opportunity</b>\n\n"
        f"From: https://x.com/{username} ({followers} followers)\n"
        f"\"{tweet_text}\"\n"
        f"Likes: {likes:,} | RTs: {rts:,} | {age:.1f}h ago\n"
        f"Score: {score:.2f} | Source: {search_type}\n"
        f"\U0001f517 {tweet_link}\n\n"
        f"What's your take? (type your thoughts, or 5 to skip)"
    )


def _build_polished_message(polished_text: str) -> str:
    """Build the polished version presentation message."""
    return (
        f"\U0001f4dd <b>Polished version:</b>\n\n"
        f"\"{polished_text}\"\n\n"
        f"1 to post | type edits for another pass | 5 to skip"
    )


async def _send_message(text: str) -> int | None:
    """Send a message and return its message_id."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["result"]["message_id"]
    except Exception:
        log.error("Failed to send Telegram message", exc_info=True)
        return None


async def _get_updates(offset: int | None = None) -> list[dict]:
    """Fetch new updates from Telegram."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    params: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json().get("result", [])
    except Exception:
        log.error("Failed to get Telegram updates", exc_info=True)
        return []


def _is_skip(text: str) -> bool:
    """Check if the user wants to skip."""
    normalized = text.strip().lower()
    return normalized in ("no", "reject", "skip", "n", "\u274c", "nah", "pass", "0", "5")


def _is_approve(text: str) -> bool:
    """Check if the user wants to approve/post."""
    normalized = text.strip().lower()
    clean = normalized.replace("\ufe0f", "").replace("\u20e3", "").strip()
    return clean == "1" or normalized in ("yes", "y", "post", "\u2705")


async def _wait_for_message(
    offset: int | None,
    chat_id: str,
    timeout_seconds: float,
    start_time: float,
) -> tuple[str | None, int | None]:
    """Wait for a message from the user. Returns (text, new_offset) or (None, offset) on timeout."""
    while True:
        elapsed = time.monotonic() - start_time
        if elapsed >= timeout_seconds:
            return None, offset

        updates = await _get_updates(offset=offset)

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg:
                continue
            if str(msg.get("chat", {}).get("id")) != chat_id:
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            # Check for pause/resume commands
            cmd = parse_pause_command(text)
            if cmd is not None:
                from tweetgod.notifier import notify_paused, notify_resumed, notify_status
                cmd_name, cmd_kwargs = cmd
                if cmd_name == "pause":
                    until = pause_for(**cmd_kwargs)
                    await notify_paused(until)
                    return "__PAUSE__", offset
                elif cmd_name == "pause_today":
                    until = pause_until_tomorrow()
                    await notify_paused(until)
                    return "__PAUSE__", offset
                elif cmd_name == "resume":
                    resume()
                    await notify_resumed()
                    continue
                elif cmd_name == "status":
                    from tweetgod.pause import get_paused_until
                    from tweetgod.dedup import get_today_post_count
                    await notify_status(get_paused_until(), get_today_post_count())
                    continue
                continue

            return text, offset

        await asyncio.sleep(5)


async def request_approval(
    candidate: ScoredTweet,
    keyword: str,
    score: float,
    search_type: str,
) -> ApprovalResult:
    """Present a tweet to the user, get their raw take, polish it, and iterate until approved or skipped."""
    global approval_active

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("Telegram not configured, skipping (no auto-post)")
        return ApprovalResult(outcome="rejected", final_text="")

    # Step 1: Present the tweet
    msg_text = _build_tweet_message(candidate, keyword, score, search_type)
    msg_id = await _send_message(msg_text)
    if msg_id is None:
        log.warning("Could not send tweet presentation, skipping")
        return ApprovalResult(outcome="rejected", final_text="")

    log.info("Tweet presented (msg_id=%d), waiting for user's take...", msg_id)

    # Flush old updates before polling
    updates = await _get_updates()
    offset = max(u["update_id"] for u in updates) + 1 if updates else None

    timeout_seconds = settings.approval_timeout_minutes * 60
    start_time = time.monotonic()
    chat_id = str(settings.telegram_chat_id)

    approval_active = True
    try:
        # Step 2: Wait for raw input
        text, offset = await _wait_for_message(offset, chat_id, timeout_seconds, start_time)

        if text is None:
            log.info("Approval timeout, skipping tweet")
            return ApprovalResult(
                outcome="timeout",
                final_text="",
                response_time_seconds=int(time.monotonic() - start_time),
            )

        if text == "__PAUSE__":
            return ApprovalResult(
                outcome="rejected",
                final_text="",
                response_time_seconds=int(time.monotonic() - start_time),
            )

        if _is_skip(text):
            log.info("Tweet skipped by user")
            return ApprovalResult(
                outcome="rejected",
                final_text="",
                response_time_seconds=int(time.monotonic() - start_time),
            )

        raw_input = text
        current_text = text

        # Step 3: Polish via LLM
        polished = await polish_quote_tweet(current_text, candidate.tweet)
        if polished is None:
            # LLM failed, use raw text as-is
            polished = current_text[:280]

        # Step 4: Present polished version and iterate
        while True:
            await _send_message(_build_polished_message(polished))

            text, offset = await _wait_for_message(offset, chat_id, timeout_seconds, start_time)

            if text is None:
                log.info("Timeout during polish iteration, skipping")
                return ApprovalResult(
                    outcome="timeout",
                    final_text="",
                    raw_input=raw_input,
                    response_time_seconds=int(time.monotonic() - start_time),
                )

            if text == "__PAUSE__":
                return ApprovalResult(
                    outcome="rejected",
                    final_text="",
                    raw_input=raw_input,
                    response_time_seconds=int(time.monotonic() - start_time),
                )

            if _is_skip(text):
                log.info("Skipped after seeing polished version")
                return ApprovalResult(
                    outcome="rejected",
                    final_text="",
                    raw_input=raw_input,
                    response_time_seconds=int(time.monotonic() - start_time),
                )

            if _is_approve(text):
                log.info("Quote tweet approved!")
                return ApprovalResult(
                    outcome="approved",
                    final_text=polished,
                    raw_input=raw_input,
                    response_time_seconds=int(time.monotonic() - start_time),
                )

            # User typed something else, could be a direct replacement or feedback
            # If it's short and clean (looks like final text), use it directly
            # If it's longer feedback/direction, send back to LLM
            if len(text) <= 280 and not any(w in text.lower() for w in ["make it", "change", "more", "less", "try", "instead"]):
                # Looks like a direct replacement — polish it lightly
                polished = await polish_quote_tweet(text, candidate.tweet)
                if polished is None:
                    polished = text[:280]
                raw_input = text
            else:
                # Looks like feedback — send back to LLM with context
                feedback_prompt = f"{current_text}\n\nFeedback: {text}"
                polished = await polish_quote_tweet(feedback_prompt, candidate.tweet)
                if polished is None:
                    polished = current_text[:280]

            current_text = text

    finally:
        approval_active = False
