"""Optional, isolated LLM interface for the final summary step's narrative text.

Per DECISIONS.md > "LLM Usage": the workflow itself is fixed and rule-based (it is
literally "the same sequence of clicks" every day), so an LLM is not used for planning,
tool selection, or anything that decides whether an action executes. The only place an
LLM could add value is turning the deterministic summary data into a friendlier
paragraph for the caseworker to read - and even there, no LLM output can trigger an
action; this module is called *after* the workflow has finished executing.

Behavior:
  - If ANTHROPIC_API_KEY is not set, generate_narrative() returns a deterministic
    template string built from the summary data. This is the default, so a clean clone
    with no API key configured still produces a complete, correct summary.
  - If ANTHROPIC_API_KEY is set, generate_narrative() attempts one call to Claude to
    phrase the same data as prose. Any failure (network, auth, rate limit, malformed
    response) falls back to the deterministic template rather than breaking the run -
    the summary step must never fail just because an optional LLM call failed.
"""

from __future__ import annotations

import os


def _deterministic_narrative(summary: dict) -> str:
    return (
        f"Morning workflow complete for {summary['run_date']}. "
        f"{summary['alerts_count']} overnight alert(s) reviewed, "
        f"{summary['appointments_today']} appointment(s) today, "
        f"{summary['reminders_sent']} reminder(s) sent, "
        f"{summary['cases_closed']} case(s) closed, "
        f"{summary['cases_escalated']} case(s) escalated, "
        f"{summary['overdue_compliance']} overdue compliance item(s) flagged, "
        f"{summary['items_skipped']} item(s) skipped due to validation or rejection."
    )


def generate_narrative(summary: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _deterministic_narrative(summary)

    try:  # pragma: no cover - exercised only when an API key is actually configured
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write one short, plain-language paragraph (max 3 sentences) "
                        "summarizing this caseworker's completed morning workflow for "
                        f"their own records. Data: {summary}"
                    ),
                }
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return text or _deterministic_narrative(summary)
    except Exception:
        return _deterministic_narrative(summary)
