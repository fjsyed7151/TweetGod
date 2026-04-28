"""Weekly self-improvement digest.

Pulls the last 7 days of reply_reviews + replied_tweets from Supabase
and produces a Telegram-formatted summary so Fajasy can see:

  - Approval rate by source (priority / trending / keyword / community)
  - Top approved handles  vs  top skipped handles
  - Skip-reason breakdown (off_topic / too_brief / wrong_angle / promo / bad)
  - Avg relevance score: approved vs skipped
  - 3-5 example skipped tweets with their reasons

Forward this to Claude every Sunday and we'll tune filters together.

The module is read-only — it never mutates state, never auto-tunes anything.
That's by design (see chat with Claude on hybrid self-learning approach).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from tweetgod.dedup import _get_client

log = logging.getLogger(__name__)

# Friendly labels for skip-reason tags persisted in reply_reviews.skip_reason.
_SKIP_LABEL = {
    "off_topic":   "off-topic",
    "too_brief":   "too brief",
    "wrong_angle": "wrong angle",
    "promo":       "promo / cause",
    "bad":         "bad (generic)",
    "":            "no reason",
}

# Min sample size before we'll publish a per-handle approval rate.
# Single-shot approvals/rejections are noise; require at least N appearances.
_MIN_HANDLE_SAMPLES = 3


def build_weekly_digest(days: int = 7) -> str:
    """Build the Telegram-formatted digest message.

    Returns "" if there's no data in the window — caller can decide whether
    to skip sending or send a "quiet week" placeholder.
    """
    client = _get_client()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    try:
        reviews_resp = (
            client.table("reply_reviews")
            .select(
                "tweet_id,author_username,outcome,source_type,score,"
                "relevance_score,skip_reason,reviewed_at,tweet_text"
            )
            .gte("reviewed_at", cutoff)
            .execute()
        )
        reviews = reviews_resp.data or []
    except Exception:
        log.error("Digest: failed to fetch reply_reviews", exc_info=True)
        return ""

    if not reviews:
        return (
            f"📊 <b>Weekly digest ({days}d)</b>\n\n"
            f"No candidates reviewed in the last {days} days. "
            f"Bot may have been paused or filters may be too tight."
        )

    total = len(reviews)
    approved = [r for r in reviews if r.get("outcome") == "approved"]
    skipped = [r for r in reviews if r.get("outcome") in ("rejected", "timeout")]
    n_appr = len(approved)
    n_skip = len(skipped)
    appr_rate = (n_appr / total * 100) if total else 0.0

    # ── Approval rate by source_type ──
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"appr": 0, "skip": 0})
    for r in reviews:
        src = r.get("source_type") or "unknown"
        if r.get("outcome") == "approved":
            by_source[src]["appr"] += 1
        else:
            by_source[src]["skip"] += 1

    source_lines = []
    for src in sorted(by_source.keys()):
        d = by_source[src]
        tot = d["appr"] + d["skip"]
        rate = (d["appr"] / tot * 100) if tot else 0.0
        source_lines.append(
            f"  • {src}: {d['appr']}/{tot} ({rate:.0f}%)"
        )

    # ── Per-handle approval rate ──
    by_handle: dict[str, dict[str, int]] = defaultdict(lambda: {"appr": 0, "skip": 0})
    for r in reviews:
        h = r.get("author_username") or "unknown"
        if r.get("outcome") == "approved":
            by_handle[h]["appr"] += 1
        else:
            by_handle[h]["skip"] += 1

    eligible_handles = [
        (h, d) for h, d in by_handle.items()
        if (d["appr"] + d["skip"]) >= _MIN_HANDLE_SAMPLES
    ]
    eligible_handles.sort(
        key=lambda x: (
            x[1]["appr"] / max(x[1]["appr"] + x[1]["skip"], 1),
            x[1]["appr"],
        ),
        reverse=True,
    )

    top_lines = []
    for h, d in eligible_handles[:8]:
        tot = d["appr"] + d["skip"]
        rate = d["appr"] / tot * 100
        top_lines.append(f"  • @{h}: {d['appr']}/{tot} ({rate:.0f}%)")

    bot_lines = []
    for h, d in reversed(eligible_handles[-8:]) if len(eligible_handles) > 8 else []:
        tot = d["appr"] + d["skip"]
        rate = d["appr"] / tot * 100
        bot_lines.append(f"  • @{h}: {d['appr']}/{tot} ({rate:.0f}%)")
    # Edge case: small handle set — show worst even if list is short.
    if not bot_lines and eligible_handles:
        worst = eligible_handles[-3:]
        for h, d in reversed(worst):
            tot = d["appr"] + d["skip"]
            rate = d["appr"] / tot * 100
            bot_lines.append(f"  • @{h}: {d['appr']}/{tot} ({rate:.0f}%)")

    # ── Skip-reason breakdown ──
    skip_reasons = Counter(r.get("skip_reason") or "" for r in skipped)
    reason_lines = []
    for tag, count in skip_reasons.most_common():
        label = _SKIP_LABEL.get(tag, tag or "no reason")
        pct = (count / n_skip * 100) if n_skip else 0.0
        reason_lines.append(f"  • {label}: {count} ({pct:.0f}%)")

    # ── Relevance score: approved vs skipped ──
    appr_rels = [r["relevance_score"] for r in approved if r.get("relevance_score") is not None]
    skip_rels = [r["relevance_score"] for r in skipped if r.get("relevance_score") is not None]
    appr_avg = (sum(appr_rels) / len(appr_rels)) if appr_rels else 0.0
    skip_avg = (sum(skip_rels) / len(skip_rels)) if skip_rels else 0.0

    # ── Example skipped tweets with reasons (most recent 4 with non-empty reason) ──
    examples = [
        r for r in skipped
        if r.get("skip_reason") and r.get("tweet_text")
    ]
    examples.sort(key=lambda r: r.get("reviewed_at", ""), reverse=True)
    example_lines = []
    for r in examples[:4]:
        text = (r.get("tweet_text") or "")[:140]
        if len(r.get("tweet_text") or "") > 140:
            text += "..."
        label = _SKIP_LABEL.get(r.get("skip_reason"), r.get("skip_reason"))
        author = r.get("author_username") or "?"
        example_lines.append(f"  • [{label}] @{author}: \"{text}\"")

    # ── Assemble ──
    parts = [
        f"📊 <b>Weekly digest ({days}d)</b>",
        "",
        f"<b>Volume:</b> {total} reviewed | {n_appr} approved ({appr_rate:.0f}%) | {n_skip} skipped",
        f"<b>Avg relevance score:</b> approved={appr_avg:.1f}/10 vs skipped={skip_avg:.1f}/10",
    ]
    if source_lines:
        parts += ["", "<b>Approval rate by source:</b>", *source_lines]
    if top_lines:
        parts += ["", f"<b>Top handles</b> (≥{_MIN_HANDLE_SAMPLES} samples):", *top_lines]
    if bot_lines:
        parts += ["", "<b>Worst handles</b> (consider demoting):", *bot_lines]
    if reason_lines:
        parts += ["", "<b>Skip reasons:</b>", *reason_lines]
    if example_lines:
        parts += ["", "<b>Recent skipped examples:</b>", *example_lines]
    parts += [
        "",
        "Forward to Claude → tune filters / prompts / handle list.",
    ]
    return "\n".join(parts)
