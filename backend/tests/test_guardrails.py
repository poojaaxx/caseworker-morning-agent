from __future__ import annotations

import pytest

from app.db import get_case
from app.guardrails import AmbiguousDecisionError, parse_decision
from app.models import Decision, RunStatus, StepOutcome
from app.orchestrator import ApprovalError
from app.tools.base import ToolResult
from app.workflow import WORKFLOW


def _tool(step_id: str):
    return next(s.tool for s in WORKFLOW if s.tool.id == step_id)


def _drive_to_step(orchestrator, step_id: str, target_id=None, default="approve"):
    """Approve everything else until the run pauses on the specific action instance
    under test, then stop (leave it pending, unanswered)."""
    orchestrator.start()
    guard = 0
    while orchestrator.status == RunStatus.AWAITING_APPROVAL and guard < 50:
        guard += 1
        p = orchestrator.pending
        if p.step_id == step_id and p.target_id == target_id:
            return orchestrator
        orchestrator.submit_approval(p.step_id, p.target_id, default)
    raise AssertionError(f"run never paused on {step_id}/{target_id}")


@pytest.mark.parametrize("raw", [None, 123, True, [], {}, "", "yes", "y", "APPROVE",
                                  "approve please", "reject!!"])
def test_parse_decision_rejects_anything_ambiguous(raw):
    with pytest.raises(AmbiguousDecisionError):
        parse_decision(raw)


@pytest.mark.parametrize("raw,expected", [("approve", Decision.APPROVE), ("reject", Decision.REJECT)])
def test_parse_decision_accepts_exact_values(raw, expected):
    assert parse_decision(raw) == expected


def test_irreversible_action_pauses_the_run(make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)
    assert orchestrator.status == RunStatus.AWAITING_APPROVAL
    assert orchestrator.pending is not None
    assert orchestrator.pending.step_id == "close_resolved_cases"


def test_approve_executes_the_action(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)
    orchestrator.submit_approval("close_resolved_cases", 1, "approve")
    assert get_case(conn, 1).status == "closed"


def test_reject_prevents_execution(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)
    orchestrator.submit_approval("close_resolved_cases", 1, "reject")
    assert get_case(conn, 1).status == "resolved"  # unchanged, not "closed"


def test_malformed_decision_does_not_execute_and_leaves_run_paused(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)

    for bad in ["yes", "", None, "APPROVE", 1]:
        with pytest.raises(ApprovalError):
            orchestrator.submit_approval("close_resolved_cases", 1, bad)
        assert orchestrator.status == RunStatus.AWAITING_APPROVAL
        assert get_case(conn, 1).status == "resolved"


def test_duplicate_approval_submission_is_rejected(make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)
    orchestrator.submit_approval("close_resolved_cases", 1, "approve")

    with pytest.raises(ApprovalError):
        # Same action instance, already decided; re-submitting must not re-execute.
        orchestrator.submit_approval("close_resolved_cases", 1, "approve")


def test_approval_for_non_pending_action_is_rejected(make_orchestrator):
    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)

    # Nothing is pending for escalate_urgent_case yet - approving it now must fail
    # rather than silently authorizing a future action ahead of time.
    with pytest.raises(ApprovalError):
        orchestrator.submit_approval("escalate_urgent_case", 2, "approve")


def test_irreversible_action_cannot_bypass_approval(conn, make_orchestrator, monkeypatch):
    """Directly proves the guardrail can't be routed around: execute_one() on an
    irreversible tool is never called except through an authorized approval."""
    tool = _tool("close_resolved_cases")
    calls = []

    def spy(ctx, case):
        calls.append(case.id)
        return ToolResult(outcome=StepOutcome.SUCCESS, summary="stub")

    monkeypatch.setattr(tool, "execute_one", spy)

    orchestrator = make_orchestrator()
    _drive_to_step(orchestrator, "close_resolved_cases", 1)
    assert calls == []  # not called just by pausing

    with pytest.raises(ApprovalError):
        orchestrator.submit_approval("close_resolved_cases", 1, "not-a-real-decision")
    assert calls == []  # not called on malformed input

    orchestrator.submit_approval("close_resolved_cases", 1, "reject")
    assert calls == []  # not called on reject
