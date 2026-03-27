"""Pause state management for TweetGod."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import pytz

from tweetgod.config import settings

log = logging.getLogger(__name__)

_paused_until: datetime | None = None


def is_paused() -> bool:
    """Return True if the bot is currently paused."""
    global _paused_until
    if _paused_until is None:
        return False
    tz = pytz.timezone(settings.timezone)
    now = datetime.now(tz)
    if now >= _paused_until:
        _paused_until = None
        return False
    return True


def pause_for(hours: int = 0, minutes: int = 0) -> datetime:
    """Pause for the given duration. Returns the pause-until time."""
    global _paused_until
    tz = pytz.timezone(settings.timezone)
    _paused_until = datetime.now(tz) + timedelta(hours=hours, minutes=minutes)
    log.info("Paused until %s", _paused_until.strftime("%I:%M %p %Z"))
    return _paused_until


def pause_until_tomorrow() -> datetime:
    """Pause until midnight in the configured timezone."""
    global _paused_until
    tz = pytz.timezone(settings.timezone)
    now = datetime.now(tz)
    _paused_until = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    log.info("Paused until %s", _paused_until.strftime("%I:%M %p %Z"))
    return _paused_until


def resume() -> None:
    """Clear the pause state."""
    global _paused_until
    _paused_until = None
    log.info("Resumed")


def get_paused_until() -> datetime | None:
    """Return the pause-until time, or None if not paused."""
    if is_paused():
        return _paused_until
    return None


def format_remaining() -> str:
    """Return a human-readable string like '1h 23m remaining'."""
    until = get_paused_until()
    if until is None:
        return "Not paused"
    tz = pytz.timezone(settings.timezone)
    remaining = until - datetime.now(tz)
    total_seconds = max(int(remaining.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}m remaining"
    return f"{minutes}m remaining"


def parse_pause_command(text: str) -> tuple[str, dict] | None:
    """Parse a /pause or /resume or /status command.

    Returns (command, kwargs) or None if not a command.
    - ("pause", {"hours": 2}) for /pause 2h
    - ("pause_today", {}) for /pause today
    - ("resume", {}) for /resume
    - ("status", {}) for /status
    """
    text = text.strip()

    if text == "/resume":
        return ("resume", {})

    if text == "/status":
        return ("status", {})

    if not text.startswith("/pause"):
        return None

    args = text[len("/pause"):].strip()

    if not args:
        # Default: pause for 2 hours
        return ("pause", {"hours": 2, "minutes": 0})

    if args == "today":
        return ("pause_today", {})

    # Parse duration: 2h, 30m, 1h30m, etc.
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m?)?", args)
    if match and (match.group(1) or match.group(2)):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        return ("pause", {"hours": hours, "minutes": minutes})

    return None
