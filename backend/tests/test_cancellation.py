from __future__ import annotations

import pytest

from app.db import get_case
from app.models import RunStatus
from app.orchestrator import ApprovalError


def test_cancel_while_awaiting_approval_stops_the_run(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.start()
    assert orchestrator.status == RunStatus.AWAITING_APPROVAL

    orchestrator.cancel()

    assert orchestrator.status == RunStatus.CANCELLED
    assert orchestrator.pending is None


def test_cancel_does_not_execute_the_pending_irreversible_action(conn, make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.start()  # pauses on the first irreversible action (a reminder)
    orchestrator.cancel()

    # None of the irreversible actions should have executed.
    assert get_case(conn, 1).status == "resolved"  # not "closed"
    assert get_case(conn, 2).status == "active"  # not "escalated"


def test_cannot_approve_after_cancel(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.start()
    pending = orchestrator.pending
    orchestrator.cancel()

    with pytest.raises(ApprovalError):
        orchestrator.submit_approval(pending.step_id, pending.target_id, "approve")


def test_cannot_cancel_an_already_completed_run(make_orchestrator):
    from tests.helpers import run_to_completion

    orchestrator = make_orchestrator()
    run_to_completion(orchestrator)
    assert orchestrator.status == RunStatus.COMPLETED

    with pytest.raises(ApprovalError):
        orchestrator.cancel()


def test_cannot_cancel_twice(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.start()
    orchestrator.cancel()

    with pytest.raises(ApprovalError):
        orchestrator.cancel()


def test_cancel_run_via_api(client):
    res = client.post("/api/runs", json={})
    run_id = res.json()["run_id"]

    res = client.post(f"/api/runs/{run_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    res = client.post(f"/api/runs/{run_id}/cancel")
    assert res.status_code == 400
