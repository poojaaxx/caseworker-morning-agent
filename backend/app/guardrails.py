"""The human-approval guardrail: the one boundary normal agent execution cannot cross.

This module is deliberately small and has no knowledge of specific steps or tools. It
answers exactly two questions:

  1. Given a raw decision value from the API, is it an unambiguous "approve" or
     "reject"? (parse_decision) Anything else raises - it is never silently treated as
     approval.
  2. Given a set of already-recorded approvals for a run, is a specific irreversible
     action instance authorized to execute right now? (is_authorized)

The orchestrator (orchestrator.py) is the only caller of is_authorized, and it calls it
immediately before invoking any tool with reversible=False. There is no other path to
executing an irreversible tool. See DECISIONS.md > "Human Approval / Guardrails" and
tests/test_guardrails.py::test_irreversible_action_cannot_bypass_approval.
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
    approvals: dict[tuple[str, str, Optional[int]], ApprovalRecord],
    run_id: str,
    step_id: str,
    target_id: Optional[int],
) -> bool:
    """True only if an explicit APPROVE decision exists for this exact action instance.

    No entry, a REJECT entry, or an entry for a different target/step all return False.
    This is the single choke point irreversible tool execution must pass through.
    """
    record = approvals.get((run_id, step_id, target_id))
    return record is not None and record.decision == Decision.APPROVE
