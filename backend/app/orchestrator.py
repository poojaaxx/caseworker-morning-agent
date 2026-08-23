"""The agent/orchestrator: drives WORKFLOW step by step and enforces the human-approval
guardrail before any irreversible tool executes.

This is the one place that ties workflow.py (what steps exist), guardrails.py (whether
an irreversible action is authorized), validation.py (whether a target record is even
usable), and the tools (what each action actually does) together. Everything else in
the app is either a thin API wrapper around this, or a leaf module this depends on.

Guardrail invariant (see tests/test_guardrails.py):
    A PerCaseTool with reversible=False can only have execute_one() called from
    _execute_target(), and _execute_target() for such a tool is only ever reached from
    _process_target() after guardrails.is_authorized() returned True. There is no other
    call site. Read _process_target() below to verify this directly.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from app.db import insert_audit_entry
from app.guardrails import AmbiguousDecisionError, is_authorized, parse_decision
from app.models import (
    ApprovalRecord,
    Case,
    Decision,
    PendingApproval,
    RunStatus,
    StepOutcome,
    StepResult,
    utc_now_iso,
)
from app.tools.base import GlobalTool, PerCaseTool, ToolContext
from app.validation import validate_case
from app.workflow import WORKFLOW


_APPROVAL_META_SUFFIX = "__approval_decision"


class ApprovalError(ValueError):
    """Raised for any invalid approval submission: no matching pending action, an
    already-decided action, or (via AmbiguousDecisionError) a malformed decision."""


class Orchestrator:
    def __init__(self, conn: sqlite3.Connection, run_id: str, caseworker: str = "demo-caseworker"):
        self.conn = conn
        self.run_id = run_id
        self.ctx = ToolContext(conn=conn, run_id=run_id, caseworker=caseworker)

        self.status: RunStatus = RunStatus.RUNNING
        self.step_results: list[StepResult] = []
        self.approvals: dict[tuple[str, str, Optional[int]], ApprovalRecord] = {}
        self.pending: Optional[PendingApproval] = None

        self._step_index = 0
        self._target_queue: list[Case] = []
        self._active_tool: Optional[PerCaseTool] = None
        self._pending_case: Optional[Case] = None

    # -- public API ---------------------------------------------------------------

    def start(self) -> None:
        self._advance()

    def submit_approval(self, step_id: str, target_id: Optional[int], raw_decision: object,
                         decided_by: str = "caseworker") -> None:
        if self.pending is None or self.pending.step_id != step_id or self.pending.target_id != target_id:
            raise ApprovalError(
                "no matching pending approval for step_id="
                f"{step_id!r} target_id={target_id!r}"
            )

        key = (self.run_id, step_id, target_id)
        if key in self.approvals:
            raise ApprovalError("this action has already been decided; cannot re-submit")

        try:
            decision = parse_decision(raw_decision)
        except AmbiguousDecisionError as exc:
            # Explicitly never approval. Recorded so the audit trail shows the attempt.
            # Uses a distinct step_id (suffixed) so it can never be mistaken for a
            # completed execution of the real step by anything that aggregates the
            # audit log by (step_id, outcome) - see summary.py's count().
            self._record(f"{step_id}{_APPROVAL_META_SUFFIX}", target_id, "approval_decision",
                          StepOutcome.SKIPPED, f"rejected malformed decision input: {exc}")
            raise ApprovalError(str(exc)) from exc

        self.approvals[key] = ApprovalRecord(
            run_id=self.run_id, step_id=step_id, target_id=target_id,
            decision=decision, decided_at=utc_now_iso(), decided_by=decided_by,
        )
        # Meta-record of the decision itself, kept out of the real step's step_id
        # namespace (see comment above) - it records that a decision was made, not
        # that the action succeeded.
        self._record(f"{step_id}{_APPROVAL_META_SUFFIX}", target_id, "approval_decision",
                      StepOutcome.SUCCESS, f"human decision recorded: {decision.value}")

        case = self._pending_case
        self.pending = None
        self._pending_case = None
        self.status = RunStatus.RUNNING

        if decision == Decision.REJECT:
            action_name = self._active_tool.name if self._active_tool else step_id
            summary = "human rejected this irreversible action; not executed"
            self._record(step_id, target_id, action_name, StepOutcome.REJECTED, summary)
            self.step_results.append(
                StepResult(step_id=step_id, outcome=StepOutcome.REJECTED, summary=summary,
                           detail={"case_id": target_id})
            )
        else:
            assert self._active_tool is not None and case is not None
            self._execute_target(self._active_tool, case)

        self._advance()

    def get_state(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "step_results": [
                {"step_id": r.step_id, "outcome": r.outcome.value, "summary": r.summary,
                 "detail": r.detail}
                for r in self.step_results
            ],
            "pending_approval": (
                {
                    "step_id": self.pending.step_id,
                    "target_id": self.pending.target_id,
                    "action_description": self.pending.action_description,
                    "reason": self.pending.reason,
                    "payload": self.pending.payload,
                }
                if self.pending else None
            ),
        }

    # -- internal driver loop ------------------------------------------------------

    def _advance(self) -> None:
        while self.status == RunStatus.RUNNING:
            if self._target_queue:
                case = self._target_queue.pop(0)
                self._process_target(self._active_tool, case)
                continue

            if self._step_index >= len(WORKFLOW):
                self.status = RunStatus.COMPLETED
                return

            tool = WORKFLOW[self._step_index].tool
            self._step_index += 1
            self._start_step(tool)

    def _start_step(self, tool) -> None:
        if isinstance(tool, GlobalTool):
            self._run_global_tool(tool)
            return

        assert isinstance(tool, PerCaseTool)
        self._active_tool = tool
        try:
            self._target_queue = list(tool.get_targets(self.ctx))
        except Exception as exc:  # dependency failure while selecting targets
            summary = f"failed to determine targets: {exc}"
            self._record(tool.id, None, tool.name, StepOutcome.FAILED, summary)
            self.step_results.append(
                StepResult(step_id=tool.id, outcome=StepOutcome.FAILED, summary=summary)
            )
            self._target_queue = []

    def _run_global_tool(self, tool: GlobalTool) -> None:
        try:
            result = tool.execute(self.ctx)
        except Exception as exc:
            self._record(tool.id, None, tool.name, StepOutcome.FAILED, f"unhandled error: {exc}")
            self.step_results.append(
                StepResult(step_id=tool.id, outcome=StepOutcome.FAILED, summary=str(exc))
            )
            return

        self._record(tool.id, None, tool.name, result.outcome, result.summary, result.detail)
        self.step_results.append(
            StepResult(step_id=tool.id, outcome=result.outcome, summary=result.summary,
                       detail=result.detail)
        )

    def _process_target(self, tool: PerCaseTool, case: Case) -> None:
        validation = validate_case(case)
        if not validation.is_valid:
            summary = f"skipped case #{case.id}: validation failed ({validation.errors})"
            self._record(tool.id, case.id, tool.name, StepOutcome.SKIPPED, summary)
            self.step_results.append(
                StepResult(step_id=tool.id, outcome=StepOutcome.SKIPPED, summary=summary,
                           detail={"case_id": case.id, "errors": validation.errors})
            )
            return

        if tool.reversible:
            self._execute_target(tool, case)
            return

        if is_authorized(self.approvals, self.run_id, tool.id, case.id):
            self._execute_target(tool, case)
            return

        description, reason = tool.describe_action(self.ctx, case)
        self.pending = PendingApproval(
            run_id=self.run_id, step_id=tool.id, target_id=case.id,
            action_description=description, reason=reason,
            payload={"case_id": case.id, "client_name": case.client_name},
        )
        self._pending_case = case
        self._record(tool.id, case.id, tool.name, StepOutcome.PENDING_APPROVAL,
                      f"awaiting human approval: {description}")
        self.status = RunStatus.AWAITING_APPROVAL

    def _execute_target(self, tool: PerCaseTool, case: Case) -> None:
        try:
            result = tool.execute_one(self.ctx, case)
        except Exception as exc:
            self._record(tool.id, case.id, tool.name, StepOutcome.FAILED, f"unhandled error: {exc}")
            self.step_results.append(
                StepResult(step_id=tool.id, outcome=StepOutcome.FAILED, summary=str(exc),
                           detail={"case_id": case.id})
            )
            return

        self._record(tool.id, case.id, tool.name, result.outcome, result.summary, result.detail)
        self.step_results.append(
            StepResult(step_id=tool.id, outcome=result.outcome, summary=result.summary,
                       detail=result.detail)
        )

    # -- audit ------------------------------------------------------------------

    def _record(self, step_id: str, target_id: Optional[int], action: str,
                outcome: StepOutcome, summary: str, detail: Optional[dict] = None) -> None:
        payload = dict(detail or {})
        payload.setdefault("summary", summary)
        insert_audit_entry(
            self.conn, self.run_id, utc_now_iso(), step_id, target_id, action,
            outcome.value, json.dumps(payload, default=str),
        )
