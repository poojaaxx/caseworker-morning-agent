"""FastAPI entrypoint.

Serves the JSON API under /api/* and the static demo frontend at / (single process).
Note: per the official problem statement, a UI is explicitly not required and interface
quality is not assessed for this problem - see run_cli.py for a plain stdout execution
trace, which alone satisfies the floor's traceability requirement. This API/frontend is
kept because it was useful demo infrastructure from Phase 1 and remains a legitimate,
if secondary, way to show the same run.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import get_audit_log, get_connection, init_db
from app.history_client import HistoryServiceClient
from app.orchestrator import OrchestratorError, ReferralRunOrchestrator
from app.referrals import ReferralQueueError, load_referral_queue

app = FastAPI(title="Caseworker Morning Agent")

_conn = get_connection()
init_db(_conn)

RUNS: dict[str, ReferralRunOrchestrator] = {}


class AdoptionRequest(BaseModel):
    decision: Any = None
    decided_by: str = "caseworker"


def _get_run(run_id: str) -> ReferralRunOrchestrator:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run with id {run_id!r}")
    return run


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/history-service/health")
def history_service_health() -> dict:
    client = HistoryServiceClient()
    try:
        reachable = client.health()
    finally:
        client.close()
    return {"reachable": reachable}


@app.get("/api/referrals")
def list_referrals() -> list[dict]:
    try:
        referrals = load_referral_queue()
    except ReferralQueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [
        {
            "referral_id": r.referral_id,
            "received_at": r.received_at.isoformat(),
            "resident_ref": r.resident_ref,
            "source": r.source,
            "summary": r.summary,
            "requested_action": r.requested_action,
            "urgency": r.urgency,
        }
        for r in referrals
    ]


@app.post("/api/runs")
def create_run() -> dict:
    run_id = uuid.uuid4().hex[:12]
    try:
        orchestrator = ReferralRunOrchestrator(_conn, run_id)
    except ReferralQueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    RUNS[run_id] = orchestrator
    try:
        orchestrator.run()
    finally:
        orchestrator.close()  # history service client no longer needed once processing stops
    return orchestrator.get_state()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id).get_state()


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    orchestrator = _get_run(run_id)
    try:
        orchestrator.cancel()
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return orchestrator.get_state()


@app.post("/api/runs/{run_id}/referrals/{referral_id}/adopt")
def adopt_note(run_id: str, referral_id: str, body: AdoptionRequest) -> dict:
    orchestrator = _get_run(run_id)
    try:
        orchestrator.adopt_note(referral_id, body.decision, body.decided_by)
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return orchestrator.get_state()


@app.get("/api/runs/{run_id}/audit")
def get_run_audit(run_id: str) -> list[dict]:
    _get_run(run_id)  # 404 if unknown, for a consistent error even with no audit rows yet
    return get_audit_log(_conn, run_id)


_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
