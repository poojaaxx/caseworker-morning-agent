"""FastAPI entrypoint.

Serves the JSON API under /api/* and the static demo frontend at / (single process,
single command to run - see README.md > Run instructions).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import get_all_cases, get_audit_log, get_connection, init_db
from app.orchestrator import ApprovalError, Orchestrator

app = FastAPI(title="Caseworker Morning Agent")

_conn = get_connection()
init_db(_conn)

RUNS: dict[str, Orchestrator] = {}


class StartRunRequest(BaseModel):
    caseworker: str = "demo-caseworker"


class ApprovalRequest(BaseModel):
    step_id: str
    target_id: Optional[int] = None
    decision: Any = None
    decided_by: str = "caseworker"


def _get_run(run_id: str) -> Orchestrator:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run with id {run_id!r}")
    return run


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/cases")
def list_cases() -> list[dict]:
    return [c.__dict__ for c in get_all_cases(_conn)]


@app.post("/api/runs")
def create_run(body: StartRunRequest) -> dict:
    run_id = uuid.uuid4().hex[:12]
    orchestrator = Orchestrator(_conn, run_id, caseworker=body.caseworker)
    RUNS[run_id] = orchestrator
    orchestrator.start()
    return orchestrator.get_state()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id).get_state()


@app.post("/api/runs/{run_id}/approvals")
def submit_approval(run_id: str, body: ApprovalRequest) -> dict:
    orchestrator = _get_run(run_id)
    try:
        orchestrator.submit_approval(body.step_id, body.target_id, body.decision, body.decided_by)
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return orchestrator.get_state()


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    orchestrator = _get_run(run_id)
    try:
        orchestrator.cancel()
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return orchestrator.get_state()


@app.get("/api/runs/{run_id}/audit")
def get_run_audit(run_id: str) -> list[dict]:
    _get_run(run_id)  # 404 if unknown, for a consistent error even with no audit rows yet
    return get_audit_log(_conn, run_id)


_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
