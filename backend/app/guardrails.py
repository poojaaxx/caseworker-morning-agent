"""The explicit-decision primitive, reused unchanged from Phase 1.

This module is deliberately small and has no knowledge of any specific domain. It
answers exactly one question: given a raw decision value from the API, is it an
unambiguous "approve" or "reject"? Anything else raises - it is never silently treated
as approval. Silence, timeout, "yes", wrong case, wrong type: all rejected.

In Phase 1 this also gated execution of an irreversible tool via a second function,
is_authorized(), keyed by (run_id, step_id, target_id). That function has been removed
here: the official Problem 5 domain has no tool capable of taking a
supervisor-approval-requiring action at all (see DECISIONS.md > "Structural Safety" for
why that is a stronger guarantee than an approval check could ever provide), and the
one place official policy (ACA-2026/1 2.4) does describe an explicit human decision -
"A drafted [triage] note is a proposal. It has no effect on the case until a caseworker
adopts it" - is a one-shot decision against a single already-existing referral result
(orchestrator.py's adopt_note()), not a repeatedly-consulted authorization table. Kept
here anyway as a distinct file, rather than folded into orchestrator.py, because the
"never treat an ambiguous decision as approval" rule is the one piece of this module
that generalizes beyond this specific application and is independently tested.
"""

from __future__ import annotations

from app.models import Decision


class AmbiguousDecisionError(ValueError):
    """Raised when a decision value is missing, malformed, or not exactly
    'approve'/'reject'. Callers MUST treat this as "not approved" - never as approval."""


def parse_decision(raw: object) -> Decision:
    if not isinstance(raw, str):
        raise AmbiguousDecisionError(
            f"decision must be a string, got {type(raw).__name__!r}"
        )
    normalized = raw.strip()
    if normalized == "approve":
        return Decision.APPROVE
    if normalized == "reject":
        return Decision.REJECT
    raise AmbiguousDecisionError(
        f"decision must be exactly 'approve' or 'reject', got {raw!r}"
    )
