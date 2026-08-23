# Brite Spark 2026 — The Caseworker's Morning

## Problem

> A caseworker spends the first forty minutes of every day on the same sequence of
> clicks. Build an agent that performs the whole sequence end to end and stops to ask a
> human before doing anything that cannot be undone.

This is Brite Spark 2026 Problem 5 (Agentic AI / Guardrails). No official Problem 5 data
pack was provided for this build — the workspace was empty apart from this statement, so
the specific "sequence of clicks" modeled below is a documented assumption, not an
official spec. See [DECISIONS.md](DECISIONS.md) for the full reasoning.

## Solution

An agent (orchestrator) runs a fixed, ordered 9-step morning workflow against a mock
case-management database: checking alerts, triaging the case queue, checking the
calendar, pulling case files, sending appointment reminders, flagging overdue
compliance, closing resolved cases, escalating urgent cases, and generating a summary.

Three of those steps are **irreversible** (sending a message to a client, closing a
case, escalating a case to a supervisor). Before executing any of them, the agent stops
and asks a human for an explicit `approve`/`reject` decision. This gate is enforced in
the orchestrator's code path itself — there is no route to executing an irreversible
tool without a matching, explicit approval record. See
[`backend/app/orchestrator.py`](backend/app/orchestrator.py) and
[`backend/app/guardrails.py`](backend/app/guardrails.py).

## Key features

- End-to-end agent workflow over a 9-step caseworker morning routine
- Workflow/orchestration layer separate from tools, validation, and guardrail policy
- Human-in-the-loop approval gate for irreversible actions, enforced in code
- Per-record validation (missing/malformed/invalid-state data is flagged, not guessed at)
- Failure handling for a simulated unavailable dependency, without crashing the run
- Full audit log of every step, decision, and outcome, persisted to SQLite
- Minimal web UI for running the demo end to end

## Architecture

```
Caseworker (browser)
        |
        v
   FastAPI app (backend/app/main.py)  <-- serves API (/api/*) and static UI (/)
        |
        v
   Orchestrator (orchestrator.py)  -- drives WORKFLOW step by step
        |
        +--> workflow.py        (ordered list of steps - the "sequence of clicks")
        +--> tools/*.py          (one Tool per action; declares reversible: bool)
        +--> validation.py       (per-record validation rules)
        +--> guardrails.py       (parses/authorizes human approval decisions)
        +--> db.py                (SQLite: case records + audit log)
        +--> llm.py                (optional, isolated - only phrases the final summary)
```

Each irreversible tool's `execute_one()` is only ever called from one place in
`orchestrator.py`, immediately after `guardrails.is_authorized()` returns `True` for
that exact action instance. See `DECISIONS.md > Human Approval / Guardrails`.

## Technology stack

- Python 3.11, FastAPI, SQLite (stdlib `sqlite3`)
- Plain HTML/CSS/JavaScript frontend (no build step, no framework)
- pytest for automated tests

No LLM, database server, queue, or container orchestration is required to run this
project. See `DECISIONS.md > Technology Decisions` for why.

## Prerequisites

- Python 3.10 or later
- pip

## Installation

```bash
git clone <this-repo-url>
cd caseworker-morning-agent
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuration

No configuration is required to run the project. Optionally, set `ANTHROPIC_API_KEY` to
let the final "generate daily summary" step phrase its summary via an LLM call instead
of a deterministic template — everything else about the workflow is unaffected either
way (see `DECISIONS.md > LLM Usage`). Never commit a real key; use a local `.env` if you
add one (`.env` is gitignored, `.env.example` is not).

## Run instructions

From `backend/`, with the virtual environment activated:

```bash
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000** in a browser. The database is created and seeded
automatically on first run (`data/caseworker.db`, gitignored).

## Test instructions

From `backend/`, with the virtual environment activated:

```bash
pytest
```

## Example workflow

1. Open http://127.0.0.1:8000 and click **Start morning workflow**.
2. The agent runs alert checks, queue triage, calendar check, and case-file pull
   automatically (all reversible/read-only steps).
3. It stops at the first irreversible action (e.g. sending an appointment reminder) and
   shows the proposed action, the affected case, and why approval is required.
4. Approve or reject. The agent continues to the next action needing a decision, then
   proceeds through the remaining reversible steps and produces a final summary.
5. The full audit trail (every step, decision, and outcome) is visible in the UI and via
   `GET /api/runs/{run_id}/audit`.

## Human approval example

When the agent reaches `send_appointment_reminders`, `close_resolved_cases`, or
`escalate_urgent_case` for a given case, it pauses the run (`status: awaiting_approval`)
and returns the pending action instead of executing it. The only way to make it proceed
is `POST /api/runs/{run_id}/approvals` with a body containing
`"decision": "approve"` or `"decision": "reject"` — anything else (missing, empty,
`"yes"`, wrong case, wrong type) is rejected by the API with a 400 and the run stays
paused. A rejected action is recorded and never executed; the run continues to whatever
comes next.

## Failure behavior

- A simulated case-file storage outage (one seeded case) is caught per-record; that
  step reports `partial` with the failure visible in its detail, and the rest of the
  run continues.
- Records that fail validation (missing client name, unparseable dates, unknown status)
  are skipped for the steps that need valid data, with the reason recorded in the audit
  log — never silently treated as valid.
- Malformed or ambiguous approval input is rejected by the guardrail layer itself, not
  just the UI, and is never treated as approval.
- Re-submitting a decision for an already-decided action is rejected (no duplicate
  execution).
- Unhandled tool exceptions are caught at the orchestrator level and recorded as a
  failed step; the run never reports success after a failure.

## Known limitations

- In-memory run state: an in-progress run does not survive a backend restart. Completed
  side effects (case closures, escalations, reminders already sent) are not lost or
  re-applied, because they and the audit log are written to SQLite as they happen —
  only that run's current position is lost.
- The specific 9-step workflow is a documented assumption (see Problem section above),
  not sourced from an official Problem 5 data pack.
- Single-process, single-caseworker demo; not built for concurrent multi-caseworker load.
- "Sends" and "escalations" are simulated and logged, not delivered to any real
  messaging/notification system.

## Future improvements

See `DECISIONS.md > What We Would Improve First`.

## Clean clone verification

The steps under Installation/Run/Test above are exactly what was run to verify this
project from a clean clone before submission (see `DECISIONS.md` for the verification
log/notes if this section is expanded later).
