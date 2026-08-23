"""Optional, isolated LLM interface for triage-note phrasing.

Per the official problem statement ("the discipline that pays is not hard-coding the
rules of the policy into the flow of the agent") and DECISIONS.md > "LLM Usage": whether
a note gets drafted at all is a strictly deterministic decision made by policy.py and
enforced by triage.py's guard, BEFORE this module is ever called. This module only
phrases the CONTENT of a draft that has already been authorized - it has no way to
cause a note to be drafted for a referral the guard has blocked, because triage.py
never calls it on that path at all (see triage.py's generate_triage_note).

Behavior:
  - If ANTHROPIC_API_KEY is not set (the default), generate_triage_narrative() returns
    a deterministic template built from the referral and history data. A clean clone
    with no API key produces complete, correct triage notes with zero configuration.
  - If set, it attempts one call to Claude to phrase the same facts as prose. Any
    failure (network, auth, rate limit, malformed response) falls back to the
    deterministic template - drafting must never fail just because an optional LLM
    call failed.
"""

from __future__ import annotations

import os

from app.models import HistoryFetchOutcome, HistoryFetchResult, Referral


def _deterministic_narrative(referral: Referral, history: HistoryFetchResult) -> str:
    lines = [
        f"Referral {referral.referral_id} ({referral.source}, urgency: {referral.urgency}).",
        f"Resident {referral.resident_ref}. Requested action: {referral.requested_action}.",
        f"Summary: {referral.summary}",
    ]
    if history.outcome == HistoryFetchOutcome.OK and history.record:
        rec = history.record
        lines.append(
            f"Current status: {rec.status}, benefit {rec.benefit_code}, "
            f"district {rec.district}, award GBP {rec.award_monthly:.2f}/month."
        )
        lines.append(f"Household size: {len(rec.household)}. Recent events: {len(rec.events)}.")
    else:
        lines.append(
            f"Resident history could not be retrieved ({history.error or history.outcome.value})."
        )
    lines.append("Recommended next step: caseworker review per requested action above.")
    return " ".join(lines)


def generate_triage_narrative(referral: Referral, history: HistoryFetchResult) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _deterministic_narrative(referral, history)

    try:  # pragma: no cover - exercised only when an API key is actually configured
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        history_summary = (
            f"status={history.record.status}, household_size={len(history.record.household)}, "
            f"recent_events={len(history.record.events)}"
            if history.outcome == HistoryFetchOutcome.OK and history.record
            else f"history unavailable: {history.error or history.outcome.value}"
        )
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write a short, plain-language triage note (max 4 sentences) for "
                        "a caseworker reviewing this referral. State what the situation is "
                        "and what should happen next. Do not invent facts not given here.\n"
                        f"Referral: {referral.referral_id}, source: {referral.source}, "
                        f"urgency: {referral.urgency}\n"
                        f"Requested action: {referral.requested_action}\n"
                        f"Summary: {referral.summary}\n"
                        f"Resident history: {history_summary}"
                    ),
                }
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return text or _deterministic_narrative(referral, history)
    except Exception:
        return _deterministic_narrative(referral, history)
