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
from tweetgod.llm import polish_quote_tweet, iterate_quote_tweet
from tweetgod.pause import parse_pause_command, pause_for, pause_until_tomorrow, resume

log = logging.getLogger(__name__)

# Flag so the background command listener knows to back off during approval
approval_active = False


class ApprovalResult(BaseModel):
    outcome: str  # "approved" | "edited" | "rejected" | "timeout"
    final_text: str
    raw_input: str = ""
    response_time_seconds: int | None = None
    # Short code captured from the Telegram skip command. Empty = generic
    # skip / approved / timeout. See SKIP_REASONS below for the mapping.
    skip_reason: str = ""


# Skip-code → reason-tag mapping. The user can type any of these to log
# WHY they're skipping a candidate, fueling the weekly digest's pattern
# detection. Plain "5" = generic skip with no reason.
SKIP_REASONS: dict[str, str] = {
    "5a": "off_topic",     # wrong niche entirely
    "5b": "too_brief",     # finance-adjacent but no substance to react to
    "5c": "wrong_angle",   # on-topic but nothing to add / wrong stance
    "5d": "promo",         # community shoutouts, giveaways, cause campaigns
    "3":  "bad",           # generic "this one's bad" without a category
}


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
    rel = candidate.replyability_score

    username = candidate.tweet.author_username
    rel_str = f" | Rel: {rel:.0f}/10" if rel > 0 else ""
    return (
        f"\U0001f4ac <b>Quote Tweet Opportunity</b>\n\n"
        f"From: https://x.com/{username} ({followers} followers)\n"
        f"\"{tweet_text}\"\n"
        f"Likes: {likes:,} | RTs: {rts:,} | {age:.1f}h ago\n"
        f"Score: {score:.2f}{rel_str} | Source: {search_type}\n"
        f"\U0001f517 {tweet_link}\n\n"
        f"What's your take? (type, or 5=skip / 5a=off-topic / 5b=too brief / 5c=wrong angle / 5d=promo / 3=bad)"
    )


def _build_polished_message(polished_text: str) -> str:
    """Build the polished version presentation message."""
    return (
        f"\U0001f4dd <b>Polished version:</b>\n\n"
        f"\"{polished_text}\"\n\n"
        f"1=post | feedback for another pass | 5=skip / 5a/5b/5c/5d / 3=bad"
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


def _parse_skip(text: str) -> tuple[bool, str]:
    """Check if the user wants to skip, returning (is_skip, reason_tag).

    Reason tag is "" for plain skip, otherwise one of the values in
    SKIP_REASONS (off_topic, too_brief, wrong_angle, promo, bad).
    """
    normalized = text.strip().lower()
    if normalized in SKIP_REASONS:
        return True, SKIP_REASONS[normalized]
    if normalized in ("no", "reject", "skip", "n", "\u274c", "nah", "pass", "0", "5"):
        return True, ""
    return False, ""


def _is_skip(text: str) -> bool:
    """Back-compat shim \u2014 call _parse_skip when you also need the reason."""
    return _parse_skip(text)[0]


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

        is_skip, skip_reason = _parse_skip(text)
        if is_skip:
            log.info("Tweet skipped by user (reason=%r)", skip_reason or "generic")
            return ApprovalResult(
                outcome="rejected",
                final_text="",
                skip_reason=skip_reason,
                response_time_seconds=int(time.monotonic() - start_time),
            )

        raw_input = text

        # Step 3: First-pass polish from raw take.
        polished = await polish_quote_tweet(raw_input, candidate.tweet)
        if polished is None:
            polished = raw_input[:280]

        # Step 4: Present polished version and iterate.
        # Every subsequent non-control message is treated as FEEDBACK on the
        # current draft, never as new content to re-polish from scratch. This
        # prevents the LLM from echoing feedback verbatim ("don't repeat what
        # tweet said. feedback: try again").
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

            is_skip, skip_reason = _parse_skip(text)
            if is_skip:
                log.info("Skipped after seeing polished version (reason=%r)", skip_reason or "generic")
                return ApprovalResult(
                    outcome="rejected",
                    final_text="",
                    raw_input=raw_input,
                    skip_reason=skip_reason,
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

            # Anything else = feedback on the current draft. Apply it via the
            # iterate prompt (which knows about raw take + previous draft +
            # feedback as separate fields and is told NOT to echo feedback).
            new_draft = await iterate_quote_tweet(
                raw_take=raw_input,
                previous_draft=polished,
                feedback=text,
                tweet=candidate.tweet,
            )
            if new_draft and new_draft.strip():
                polished = new_draft

    finally:
        approval_active = False
