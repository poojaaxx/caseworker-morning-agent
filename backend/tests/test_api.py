from __future__ import annotations


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200


def test_list_referrals_returns_all_twelve(client):
    res = client.get("/api/referrals")
    assert res.status_code == 200
    assert len(res.json()) == 12


def test_create_run_processes_full_queue(client):
    res = client.post("/api/runs")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert len(body["results"]) == 12
    assert body["summary"]["escalated"] == 3
    assert body["summary"]["handoff"] == 3
    assert body["summary"]["autonomous_triaged"] == 6


def test_get_run(client):
    run_id = client.post("/api/runs").json()["run_id"]
    res = client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["run_id"] == run_id


def test_unknown_run_returns_404(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_adopt_note_via_api(client):
    state = client.post("/api/runs").json()
    autonomous = next(r for r in state["results"] if r["outcome"] == "autonomous_triaged")
    res = client.post(
        f"/api/runs/{state['run_id']}/referrals/{autonomous['referral_id']}/adopt",
        json={"decision": "approve"},
    )
    assert res.status_code == 200
    updated = next(r for r in res.json()["results"] if r["referral_id"] == autonomous["referral_id"])
    assert updated["triage_note"]["adopted"] is True


def test_adopt_note_malformed_decision_returns_400(client):
    state = client.post("/api/runs").json()
    autonomous = next(r for r in state["results"] if r["outcome"] == "autonomous_triaged")
    res = client.post(
        f"/api/runs/{state['run_id']}/referrals/{autonomous['referral_id']}/adopt",
        json={"decision": "maybe"},
    )
    assert res.status_code == 400


def test_adopt_note_on_escalated_referral_returns_400(client):
    state = client.post("/api/runs").json()
    escalated = next(r for r in state["results"] if r["outcome"] == "escalated")
    res = client.post(
        f"/api/runs/{state['run_id']}/referrals/{escalated['referral_id']}/adopt",
        json={"decision": "approve"},
    )
    assert res.status_code == 400


def test_cancel_a_completed_run_returns_400(client):
    run_id = client.post("/api/runs").json()["run_id"]
    res = client.post(f"/api/runs/{run_id}/cancel")
    assert res.status_code == 400


def test_audit_log_present_after_run(client):
    run_id = client.post("/api/runs").json()["run_id"]
    res = client.get(f"/api/runs/{run_id}/audit")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) > 12  # multiple trace events per referral
    assert any(e["action"] == "escalation_created" for e in entries)
    assert any(e["action"] == "handoff_created" for e in entries)
    assert any(e["action"] == "triage_note_drafted" for e in entries)


def test_history_service_health_endpoint(client):
    res = client.get("/api/history-service/health")
    assert res.status_code == 200
    assert res.json()["reachable"] is True
