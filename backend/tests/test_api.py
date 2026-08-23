from __future__ import annotations


def test_start_run_returns_running_state(client):
    res = client.post("/api/runs", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"]
    assert body["status"] in ("running", "awaiting_approval", "completed")


def test_full_run_via_api_reaches_completed(client):
    res = client.post("/api/runs", json={})
    state = res.json()
    run_id = state["run_id"]

    guard = 0
    while state["status"] == "awaiting_approval" and guard < 50:
        guard += 1
        pending = state["pending_approval"]
        res = client.post(
            f"/api/runs/{run_id}/approvals",
            json={"step_id": pending["step_id"], "target_id": pending["target_id"], "decision": "approve"},
        )
        assert res.status_code == 200
        state = res.json()

    assert state["status"] == "completed"


def test_malformed_decision_returns_400_and_does_not_advance(client):
    res = client.post("/api/runs", json={})
    state = res.json()
    run_id = state["run_id"]
    pending = state["pending_approval"]

    res = client.post(
        f"/api/runs/{run_id}/approvals",
        json={"step_id": pending["step_id"], "target_id": pending["target_id"], "decision": "maybe"},
    )
    assert res.status_code == 400

    res = client.get(f"/api/runs/{run_id}")
    assert res.json()["status"] == "awaiting_approval"
    assert res.json()["pending_approval"] == pending


def test_unknown_run_id_returns_404(client):
    res = client.get("/api/runs/does-not-exist")
    assert res.status_code == 404


def test_duplicate_approval_returns_400(client):
    res = client.post("/api/runs", json={})
    state = res.json()
    run_id = state["run_id"]
    pending = state["pending_approval"]
    payload = {"step_id": pending["step_id"], "target_id": pending["target_id"], "decision": "approve"}

    res = client.post(f"/api/runs/{run_id}/approvals", json=payload)
    assert res.status_code == 200

    # The decision already advanced past this action - the API must not silently accept
    # (or worse, re-execute) a second submission for the same action instance.
    res = client.post(f"/api/runs/{run_id}/approvals", json=payload)
    assert res.status_code == 400


def test_audit_log_available_after_run(client):
    res = client.post("/api/runs", json={})
    run_id = res.json()["run_id"]
    res = client.get(f"/api/runs/{run_id}/audit")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) > 0
