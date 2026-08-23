"""Triage note drafting (ACA-2026/1 2.4) and its ACA-2026/2 3.9 guard.

The guard lives here, not only in the orchestrator, because ACA-2026/1 2.2 says the
restriction "applies to the drafting of the note itself, not merely to its adoption."
generate_triage_note() is the ONLY function in this codebase that produces triage-note
text, and it refuses outright - before generating anything, including via the optional
LLM path in llm.py - if given a HandoffDecision that says 3.9 applies. There is no
"unchecked" variant and no parameter that bypasses the check; the check is the first
thing the function does. See tests/test_triage_guard.py, which calls this function
directly (not through the orchestrator) to prove the refusal cannot be routed around.
"""

from __future__ import annotations

from app.llm import generate_triage_narrative
from app.models import HandoffVerdict, HistoryFetchResult, HandoffDecision, Referral, TriageNote


class TriageBlockedError(RuntimeError):
    """Raised by generate_triage_note() when ACA-2026/1 3.9 applies. This is not a
    validation warning the caller can ignore - callers must not catch this and draft
    anyway; the orchestrator treats it as confirmation that no note exists, not as a
    failure to recover from."""


def generate_triage_note(
    referral: Referral, history: HistoryFetchResult, handoff_decision: HandoffDecision,
) -> TriageNote:
    if handoff_decision.verdict == HandoffVerdict.HANDOFF_REQUIRED:
        raise TriageBlockedError(
            f"drafting a triage note for {referral.referral_id} is prohibited: "
            f"{handoff_decision.basis.reference if handoff_decision.basis else 'ACA-2026/1 3.9'}"
        )

    narrative = generate_triage_narrative(referral, history)
    return TriageNote(
        referral_id=referral.referral_id,
        resident_ref=referral.resident_ref,
        narrative=narrative,
    )
