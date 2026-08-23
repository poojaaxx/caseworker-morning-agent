from __future__ import annotations

from app.db import get_case
from app.models import RunStatus, StepOutcome
from app.workflow import WORKFLOW
from tests.helpers import run_to_completion


def test_happy_path_full_run_completes(make_orchestrator):
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)  # approve everything

    assert orchestrator.status == RunStatus.COMPLETED
    step_ids_seen = {r.step_id for r in orchestrator.step_results}
    for step in WORKFLOW:
        assert step.tool.id in step_ids_seen, f"missing result for {step.tool.id}"


def test_happy_path_counts_are_not_double_counted(conn, make_orchestrator):
    """Regression test: the audit entry recording a human's approval decision must
    never be mistaken for a second successful execution of the underlying action."""
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator, decisions={
        ("escalate_urgent_case", 2): "reject",
    })

    reminder_successes = [
        r for r in orchestrator.step_results
        if r.step_id == "send_appointment_reminders" and r.outcome == StepOutcome.SUCCESS
    ]
    # Targets are cases 3, 4, 7, 9 with appointment_today=True; case 4 is skipped for
    # a missing client_name, leaving exactly 3 valid targets to approve.
    assert len(reminder_successes) == 3

    close_successes = [
        r for r in orchestrator.step_results
        if r.step_id == "close_resolved_cases" and r.outcome == StepOutcome.SUCCESS
    ]
    assert len(close_successes) == 1  # only case 1 is status=resolved

    escalate_successes = [
        r for r in orchestrator.step_results
        if r.step_id == "escalate_urgent_case" and r.outcome == StepOutcome.SUCCESS
    ]
    assert len(escalate_successes) == 0  # rejected, must not count as executed


def test_reversible_steps_run_without_any_approval(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.start()

    reversible_ids = {"check_alerts", "triage_queue", "check_calendar", "pull_case_files"}
    seen = {r.step_id for r in orchestrator.step_results}
    assert reversible_ids.issubset(seen)
    assert orchestrator.status == RunStatus.AWAITING_APPROVAL  # paused at the first irreversible step


def test_close_resolved_case_persists_new_status(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    case = get_case(conn, 1)
    assert case.status == "closed"


def test_rejected_escalation_leaves_case_status_unchanged(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator, decisions={("escalate_urgent_case", 2): "reject"})

    case = get_case(conn, 2)
    assert case.status == "active"  # never changed to "escalated"
