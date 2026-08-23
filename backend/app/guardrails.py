"""The explicit-decision primitive, reused unchanged from Phase 1.

This module is deliberately small and has no knowledge of any specific domain. It
answers exactly two questions:

  1. Given a raw decision value from the API, is it an unambiguous "approve" or
     "reject"? (parse_decision) Anything else raises - it is never silently treated as
     approval. Silence, timeout, "yes", wrong case, wrong type: all rejected.
  2. Given a set of already-recorded decisions for a run, is a specific action instance
     authorized right now? (is_authorized)

In Phase 1 this gated execution of an irreversible tool. In the official Problem 5
domain (see orchestrator.py), the agent has no tool capable of taking a
supervisor-approval-requiring action at all - see DECISIONS.md > "Structural safety" for
why that is a stronger guarantee than an approval check could ever provide. This module
is instead reused for the one place official policy (ACA-2026/1 2.4) does describe an
explicit human decision: "A drafted [triage] note is a proposal. It has no effect on the
case until a caseworker adopts it." adopt_note() in orchestrator.py is that decision
point, and it is the only caller of parse_decision/is_authorized.
"""

from __future__ import annotations

from typing import Optional

from app.models import ApprovalRecord, Decision


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


def is_authorized(
    approvals: dict[tuple[str, str, Optional[str]], ApprovalRecord],
    run_id: str,
    step_id: str,
    target_id: Optional[str],
) -> bool:
    """True only if an explicit APPROVE decision exists for this exact action instance.

    No entry, a REJECT entry, or an entry for a different target/step all return False.
    """
    record = approvals.get((run_id, step_id, target_id))
    return record is not None and record.decision == Decision.APPROVE
