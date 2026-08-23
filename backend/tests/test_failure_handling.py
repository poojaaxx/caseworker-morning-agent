from __future__ import annotations

from app.models import RunStatus, StepOutcome
from app.tools.base import ToolResult
from app.workflow import WORKFLOW
from tests.helpers import run_to_completion


def _tool(step_id: str):
    return next(s.tool for s in WORKFLOW if s.tool.id == step_id)


def test_simulated_dependency_failure_is_reported_not_crashed(make_orchestrator):
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    pull = next(r for r in orchestrator.step_results if r.step_id == "pull_case_files")
    assert pull.outcome == StepOutcome.PARTIAL  # never silently SUCCESS despite a failure
    failed_ids = [f["id"] for f in pull.detail["failed"]]
    assert 9 in failed_ids  # case 9 is seeded to simulate an unavailable dependency

    # The rest of the workflow must still have run to completion.
    assert orchestrator.status == RunStatus.COMPLETED


def test_invalid_case_is_skipped_not_silently_treated_as_valid(make_orchestrator):
    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    reminder_results = [r for r in orchestrator.step_results
                         if r.step_id == "send_appointment_reminders"]
    skipped = [r for r in reminder_results if r.outcome == StepOutcome.SKIPPED]
    assert len(skipped) == 1
    assert "case #4" in skipped[0].summary
    assert "missing_client_name" in skipped[0].summary


def test_unhandled_exception_in_global_tool_is_caught_and_recorded(make_orchestrator, monkeypatch):
    tool = _tool("check_calendar")

    def boom(ctx):
        raise RuntimeError("calendar service unreachable")

    monkeypatch.setattr(tool, "execute", boom)

    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    failed = next(r for r in orchestrator.step_results if r.step_id == "check_calendar")
    assert failed.outcome == StepOutcome.FAILED
    assert "calendar service unreachable" in failed.summary
    # The run must still proceed past the failure rather than crashing entirely.
    assert orchestrator.status == RunStatus.COMPLETED


def test_unhandled_exception_in_per_case_tool_does_not_crash_the_run(make_orchestrator, monkeypatch):
    tool = _tool("close_resolved_cases")

    def boom(ctx, case):
        raise RuntimeError("case management system timeout")

    monkeypatch.setattr(tool, "execute_one", boom)

    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    failed = [r for r in orchestrator.step_results
              if r.step_id == "close_resolved_cases" and r.outcome == StepOutcome.FAILED]
    assert len(failed) == 1
    assert "case management system timeout" in failed[0].summary
    assert orchestrator.status == RunStatus.COMPLETED


def test_get_targets_failure_is_caught_and_step_continues(make_orchestrator, monkeypatch):
    tool = _tool("escalate_urgent_case")

    def boom(ctx):
        raise RuntimeError("case queue unavailable")

    monkeypatch.setattr(tool, "get_targets", boom)

    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)

    failed = next(r for r in orchestrator.step_results if r.step_id == "escalate_urgent_case")
    assert failed.outcome == StepOutcome.FAILED
    assert orchestrator.status == RunStatus.COMPLETED
