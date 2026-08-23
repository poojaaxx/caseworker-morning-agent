# Decisions

This file is maintained throughout development, not written at the end. Entries are
added as decisions are made, in roughly chronological order within each section.

## Initial Project Direction

**Context:** The workspace was empty at project start — no official Problem 5 document
or data pack was provided beyond the problem statement itself:

> "A caseworker spends the first forty minutes of every day on the same sequence of
> clicks. Build an agent that performs the whole sequence end to end and stops to ask a
> human before doing anything that cannot be undone."

**Decision:** Build against this statement only. The specific "sequence of clicks" (what
a caseworker's morning routine actually consists of) is not specified anywhere in the
workspace, so it is an **assumption**, not an official requirement. We modeled a
realistic, generic caseworker morning routine (see "Agent Design" below) based on common
case-management workflows (intake/alerts triage, calendar review, case file review,
client communication, compliance checks, case closure, escalation, summary reporting).
If the organizers provided a specific workflow elsewhere, this system's workflow steps
would need to be swapped for the real ones — the architecture is built so that swap is
localized to `backend/app/workflow.py` and the `backend/app/tools/` package.

**Alternatives considered:** Wait and ask for clarification before building anything.
**Reason rejected:** The hackathon brief explicitly instructs building a "clean, modular
prototype around the stated requirement" when the detailed pack is absent, and to
document assumptions rather than block. Time is a scored constraint.

**Tradeoff:** The demo's specific workflow steps may not match what judges expect from a
real caseworker's day. We mitigate this by making the steps, tools, and irreversibility
policy trivially swappable, and by being explicit in the demo/README that this is a
documented assumption.

## Architecture Decisions

**Decision:** Orchestrator (agent) drives a fixed, ordered list of workflow steps. Each
step wraps one "tool" (an action). Steps are deterministic and rule-based, not
LLM-planned — see "LLM Usage" below.

**Decision:** The guardrail (irreversible-action / human-approval gate) is enforced
*inside the orchestrator's step-execution loop*, not in the API layer or the UI. A tool
declares `reversible: bool`. Before the orchestrator calls a non-reversible tool, it
checks for an explicit, matching `ApprovalDecision` record; if none exists it pauses the
run (`awaiting_approval`) and returns without executing the tool. There is no code path
that calls a non-reversible tool's `execute()` without going through this check — this
is what "enforced in code, not just displayed in the UI" means here, and it's covered by
`test_guardrails.py::test_irreversible_action_cannot_bypass_approval`, which calls the
orchestrator's internal execution path directly.

**Decision:** Run state (current step, pending approval, results so far) is kept
**in-memory** in the FastAPI process, keyed by `run_id`. The audit log and case-data
mutations (case closures, escalations, reminders sent) are persisted to SQLite.

**Alternatives considered:** Persist full run state (a proper resumable state machine) to
SQLite/disk.
**Reason rejected:** Out of scope for the hackathon's floor; a single-process demo does
not need cross-restart resumability, and building a persisted state machine well would
cost time better spent on the guardrail, validation, and tests.
**Tradeoff / known limitation:** If the backend process restarts while a run is
mid-flight, that run's in-progress position is lost (a new run must be started). Nothing
already executed is lost or re-applied, because completed side effects (case closures,
reminders, escalations) are written to SQLite as they happen and the audit log is
authoritative. This is listed under "Known Limitations" below and would be the first
thing to fix for production use.

## Technology Decisions

- **Python + FastAPI**: simple, reliable, minimal moving parts, easy for a stranger to
  run from a clean clone with `pip install -r requirements.txt`.
- **SQLite**: only persistence actually needed (case records + audit log); zero setup,
  ships with Python.
- **Plain HTML/CSS/JS frontend** (no framework/build step): keeps clean-clone setup to
  "open a file / one static file server," reduces failure surface for the demo.
- **No LLM dependency by default**: the workflow is a fixed, known sequence ("the same
  sequence of clicks"), so a rule-based deterministic planner is the right tool, not an
  LLM. See "LLM Usage."
- Rejected: Kubernetes, Redis, a frontend framework, vector DB, message queue — none of
  these are needed for a fixed 9-step sequential workflow over a handful of case
  records, and the rubric does not reward technology count.

## Agent Design

The orchestrator runs a fixed 9-step workflow per run, based on a generic caseworker's
morning (documented assumption, see above):

1. `check_alerts` — read overnight system alerts (new referrals, missed check-ins).
   Reversible (read-only).
2. `triage_queue` — sort/prioritize today's case queue by urgency. Reversible
   (read-only + in-memory ordering).
3. `check_calendar` — pull today's scheduled appointments/visits. Reversible (read-only).
4. `pull_case_files` — load case files for today's appointments; run validation over
   them. Reversible (read-only), but flags malformed/incomplete records.
5. `send_appointment_reminders` — send reminder messages to clients with an appointment
   today. **Irreversible** — once a message is sent to a client it cannot be unsent.
   Requires approval.
6. `flag_overdue_compliance` — identify cases with a compliance deadline in the past.
   Reversible (read-only + internal flag).
7. `close_resolved_cases` — close case files marked resolved. **Irreversible** — closing
   a case is a significant status change with downstream reporting/funding effects and
   is not meant to be casually undone. Requires approval per case.
8. `escalate_urgent_case` — escalate a case flagged high-risk to a supervisor.
   **Irreversible** — notifies another party outside the system. Requires approval.
9. `generate_daily_summary` — produce a summary of the run for the caseworker.
   Reversible (an internal artifact; can be regenerated).

Each step is implemented as a `Tool` (see `backend/app/tools/`) registered in a small
registry, so a new step/tool can be added without touching unrelated steps.

## Human Approval / Guardrails

**Decision:** Approval must be an explicit string equal to `"approve"` or `"reject"`.
Anything else — missing field, empty string, `"yes"`, `"ok"`, wrong case, timeout,
malformed JSON — is rejected by the API (422/400) and never reaches the orchestrator as
a decision, so it can never be interpreted as approval. This directly satisfies the
"silence/timeout/malformed/ambiguous is never approval" requirement.

**Decision:** Approval decisions are recorded per exact action instance (`run_id` +
`step_id` + `target_id` where relevant, e.g. a specific case being closed), not per
step-type. Approving "close case #3" does not approve closing case #7. A decision, once
recorded, is immutable — re-submitting a decision for an already-decided action is
rejected (prevents duplicate execution / re-approval races).

**Decision:** On rejection, the orchestrator marks that action `rejected` in the audit
log, does **not** execute the tool, and continues the workflow to the next step (the
run does not abort entirely just because one irreversible action was declined) — unless
the rejected action was load-bearing for a later step, in which case the later step is
skipped with a recorded reason. This is a judgement call: rejecting "send reminders" for
one client shouldn't block closing an unrelated resolved case.

## Data Handling

Mock case data is seeded into SQLite from `backend/app/seed_data.py` on first run.
Seed data deliberately includes messy/ugly records to exercise validation and error
handling: a case with a missing client name, a case with an invalid/unparseable date, a
case with a compliance deadline already in the past, a case with duplicate appointment
entries, and a case with an unknown/unexpected status value.

## Error Handling

- Validation runs over each case record before it's used in a step; invalid records are
  flagged and skipped for that step (with a reason recorded) rather than crashing the
  run or being silently treated as valid.
- Tool execution failures (simulated dependency failure, timeout) are caught at the
  orchestrator level, recorded in the audit log as a failed step, and surface to the
  caller — the run never silently reports success after a failure.
- The API validates request bodies (Pydantic) and returns 4xx with a clear message on
  malformed input rather than 500ing or guessing intent.
- A run can be explicitly cancelled at any point (`Orchestrator.cancel()` /
  `POST /api/runs/{id}/cancel`), covering "interrupted/cancelled workflow" from the
  required error-handling scope. Cancelling while an irreversible action is awaiting
  approval abandons that action (records it, never executes it) rather than either
  auto-approving or leaving the run in an ambiguous state. Cancelling a run that has
  already finished (completed or cancelled) is rejected, not silently accepted.

## Testing

Pytest covers: full happy-path run, each guardrail behavior (pause on irreversible
action, approve executes, reject blocks, malformed/ambiguous decision is rejected,
direct-call bypass is impossible), validation on malformed/missing/invalid-state
records, simulated tool failure and dependency-unavailable handling, duplicate approval
submission, run cancellation (including mid-approval), and the same guardrail/happy-path
behavior again at the HTTP API layer. 50 tests total, run via `pytest` from `backend/`.
See `backend/tests/`.

Writing this suite caught two real bugs before they shipped, both in
`orchestrator.py`: (1) the audit-log entry that records a human's approval *decision*
was originally written under the same `step_id` as the action itself with a hardcoded
`SUCCESS` outcome, which double-counted executions in the summary step and even counted
a *rejected* escalation as completed — found by
`test_workflow.py::test_happy_path_counts_are_not_double_counted`, fixed by giving the
decision-record a distinct, suffixed `step_id`. (2) two failure paths
(`get_targets()` raising, and a case skipped for failing validation) wrote to the SQLite
audit log but never appended to the in-memory `step_results` list that the API/UI
actually render, so those events would have been invisible to the caseworker in the
running app despite being in the audit trail — found by
`test_failure_handling.py::test_invalid_case_is_skipped_not_silently_treated_as_valid`,
fixed by appending a `StepResult` in both places. Both were verified fixed by the full
suite (44/44 passing) and by re-running the workflow manually before and after.

The project was also verified end to end from a genuine fresh `git clone` (see
README.md > Clean clone verification) — not just "the tests pass in the dev
environment."

## Features Rejected

- **LLM-based dynamic planning** — rejected because the workflow is a known, fixed
  sequence; introducing an LLM into planning would add nondeterminism and an external
  dependency for no behavioral benefit, working against reliability (rubric priority
  #2/#5).
- **User accounts / authentication** — rejected as out of scope; this is a single
  caseworker demo, not a multi-tenant product, and the brief explicitly discourages
  unnecessary auth complexity.
- **Persisted/resumable run state machine** — see "Architecture Decisions" above; cut for
  time, documented as a known limitation.

## Features Cut Due to Time

- **Persisted/resumable run state machine.** Run state (current step, pending
  approval) lives in-memory only. See "Architecture Decisions" and "Known Limitations."
- **Real external integrations** for reminders/escalation (an actual SMS/email
  provider, an actual supervisor-notification channel). These are simulated and
  logged only — see "What the Solution Does Not Do."
- **Multi-caseworker / authentication.** Out of scope for a single-caseworker demo;
  every run is attributed to a fixed default caseworker unless the API caller supplies
  a different name in the request body.
- **Structured application logging beyond the audit table.** The SQLite audit log is
  the system of record for what happened; there is no separate log file/format for
  operational monitoring.

Nothing on this list was mandatory functionality — the floor (agent workflow, guardrail,
validation, error handling, audit trail, tests, docs) is complete.

## Known Limitations

- In-memory run state means an in-progress run does not survive a backend restart
  (completed side effects are not lost or duplicated; only the run's position is).
- The workflow sequence is a documented assumption, not sourced from an official Problem
  5 data pack (none was present in the workspace).
- Single-caseworker, single-process demo — not built for concurrent multi-caseworker
  production load.
- (further items added as development proceeds)

## What the Solution Does Not Do

- Does not integrate with any real case-management system, email/SMS provider, or
  external agency system — all "sends"/"escalations" are simulated and logged, not
  actually delivered anywhere.
- Does not use an LLM for any decision that affects workflow execution or approval
  outcomes.
- Does not persist run state across a backend restart (see Known Limitations).

## Day-2 Surprise Requirement

- (filled in when the surprise requirement is announced and incorporated)

## What We Would Improve First

- Persist orchestrator run state (not just the audit log) so an in-progress run survives
  a restart.
- Replace the mocked "send"/"escalate" side effects with real integration adapters
  behind the existing tool interface (no orchestrator/guardrail changes needed).
- Add authentication/authorization if this were to move beyond a single-caseworker demo.
