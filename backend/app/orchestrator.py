"""The agent: processes the overnight referral queue end to end.

Per-referral pipeline (mirrors the official "morning sequence" and the execution trace
required by ACA-2026/1 5.1):

    referral_loaded -> history_retrieved -> policy_evaluated
        -> [ESCALATION_REQUIRED]  -> escalation_created -> referral_completed
        -> [else] household_evaluated
              -> [HANDOFF_REQUIRED (3.9)] -> handoff_created -> referral_completed
              -> [else]                   -> triage_note_drafted -> referral_completed

Every branch is reached from exactly one place (_process_referral below); there is no
second code path anywhere that calls triage.generate_triage_note or that performs an
escalation/hand-off. Read this file top to bottom to verify that directly - it is short
enough to audit in one sitting, which is itself part of the safety argument (see
DECISIONS.md > "Structural safety").

A referral that ends up ESCALATED or HANDOFF never reaches triage note generation at
all (4.1: "must not perform the action, must not perform a partial or preparatory
version of it" - drafting a note is exactly the kind of preparatory step this rules
out for an escalated referral; 3.9 rules it out directly for a hand-off). Escalating or
handing off one referral never stops the loop (4.3 / amendment 4.2) - the next referral
is always attempted regardless of what happened to the previous one.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from app.db import insert_audit_entry
from app.guardrails import AmbiguousDecisionError, parse_decision
from app.history_client import HistoryServiceClient
from app.models import (
    ActionVerdict,
    Decision,
    EscalationRecord,
    HandoffRecord,
    HandoffVerdict,
    HistoryFetchOutcome,
    HistoryFetchResult,
    Referral,
    ReferralOutcome,
    ReferralResult,
    RunStatus,
    utc_now_iso,
)
from app.policy import evaluate_household_for_aca_2026_2, evaluate_requested_action
from app.referrals import load_referral_queue
from app.triage import TriageBlockedError, generate_triage_note


class OrchestratorError(ValueError):
    """Raised for any invalid request against a run's current state or an adoption
    decision that is missing, malformed, already-decided, or has no matching draft."""


class ReferralRunOrchestrator:
    def __init__(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        history_client: Optional[HistoryServiceClient] = None,
        referrals: Optional[list[Referral]] = None,
    ):
        self.conn = conn
        self.run_id = run_id
        self.history_client = history_client or HistoryServiceClient()

        self.referrals = referrals if referrals is not None else load_referral_queue()
        self._queue: list[Referral] = list(self.referrals)
        self.results: list[ReferralResult] = []
        self.status = RunStatus.RUNNING

    # -- public API -----------------------------------------------------------

    def run(self) -> None:
        """Process the whole queue. Escalating or handing off a referral never stops
        this loop (ACA-2026/1 4.3, ACA-2026/2 4.2) - only cancel() does."""
        while self._queue and self.status == RunStatus.RUNNING:
            referral = self._queue.pop(0)
            self._process_referral(referral)
        if self.status == RunStatus.RUNNING:
            self.status = RunStatus.COMPLETED

    def cancel(self, cancelled_by: str = "caseworker") -> None:
        if self.status != RunStatus.RUNNING:
            raise OrchestratorError(f"cannot cancel a run that is already {self.status.value}")

        for referral in self._queue:
            self.results.append(ReferralResult(
                referral=referral, outcome=ReferralOutcome.NOT_PROCESSED,
                trace=["run_cancelled_before_reached"],
            ))
            self._record(referral.referral_id, "run_cancelled", "skipped",
                          "run cancelled before this referral was reached")
        self._queue = []
        self.status = RunStatus.CANCELLED
        self._record("__run__", "cancel_run", "skipped", f"run cancelled by {cancelled_by}")

    def adopt_note(self, referral_id: str, raw_decision: object,
                    decided_by: str = "caseworker") -> None:
        """ACA-2026/1 2.4: 'A drafted note is a proposal. It has no effect on the case
        until a caseworker adopts it.' This is that decision."""
        result = self._find_result(referral_id)
        if result is None or result.triage_note is None:
            raise OrchestratorError(f"no drafted triage note for {referral_id!r} to adopt")
        if result.triage_note.adopted is not None:
            raise OrchestratorError(f"triage note for {referral_id!r} has already been decided")

        try:
            decision = parse_decision(raw_decision)
        except AmbiguousDecisionError as exc:
            self._record(referral_id, "note_adoption_decision", "skipped",
                          f"rejected malformed decision input: {exc}")
            raise OrchestratorError(str(exc)) from exc

        result.triage_note.adopted = decision == Decision.APPROVE
        self._record(referral_id, "note_adoption_decision", "success",
                      f"decision={decision.value} by={decided_by}")

    def get_state(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "summary": self._summary(),
            "results": [self._result_to_dict(r) for r in self.results],
        }

    def close(self) -> None:
        self.history_client.close()

    # -- pipeline ---------------------------------------------------------------

    def _process_referral(self, referral: Referral) -> None:
        trace: list[str] = []

        trace.append("referral_loaded")
        self._record(referral.referral_id, "referral_loaded", "success",
                      f"{referral.referral_id} for resident {referral.resident_ref}")

        history = self.history_client.get_full_record(referral.resident_ref)
        history_ok = history.outcome == HistoryFetchOutcome.OK
        trace.append("history_retrieved" if history_ok else "history_retrieval_failed")
        self._record(
            referral.referral_id, "history_retrieved",
            "success" if history_ok else "failed",
            f"outcome={history.outcome.value}" + (f"; {history.error}" if history.error else ""),
        )

        action_decision = evaluate_requested_action(referral)
        trace.append("policy_evaluated")
        basis_text = f" basis={action_decision.basis.reference}" if action_decision.basis else ""
        self._record(referral.referral_id, "policy_evaluated", "success",
                      f"verdict={action_decision.verdict.value}{basis_text}")

        if action_decision.verdict == ActionVerdict.ESCALATION_REQUIRED:
            assert action_decision.basis is not None
            trace += ["escalation_required", "action_blocked", "escalation_created"]
            record = EscalationRecord(
                referral_id=referral.referral_id, resident_ref=referral.resident_ref,
                basis=action_decision.basis, context=self._context(referral, history),
            )
            self._record(referral.referral_id, "escalation_created", "escalated",
                          f"{action_decision.basis.reference}: {action_decision.basis.explanation}")
            self.results.append(ReferralResult(
                referral=referral, outcome=ReferralOutcome.ESCALATED, trace=trace,
                history_ok=history_ok, escalation=record,
            ))
            self._record(referral.referral_id, "referral_completed", "escalated",
                          "processing complete (escalated)")
            return

        handoff_decision = evaluate_household_for_aca_2026_2(history, referral.received_date)
        trace.append("household_evaluated")
        hbasis = f" basis={handoff_decision.basis.reference}" if handoff_decision.basis else ""
        self._record(referral.referral_id, "household_evaluated", "success",
                      f"verdict={handoff_decision.verdict.value}{hbasis}")

        if handoff_decision.verdict == HandoffVerdict.HANDOFF_REQUIRED:
            assert handoff_decision.basis is not None
            trace += ["under_18_detected" if handoff_decision.household_established
                      else "household_unknown", "ACA-2026/2_applied", "triage_generation_blocked",
                      "handoff_created"]
            record = HandoffRecord(
                referral_id=referral.referral_id, resident_ref=referral.resident_ref,
                basis=handoff_decision.basis, context=self._context(referral, history),
            )
            self._record(
                referral.referral_id, "handoff_created", "handoff",
                f"TRIAGE NOTE NOT GENERATED. Reason: {handoff_decision.basis.reference} "
                f"({handoff_decision.basis.explanation})",
            )
            self.results.append(ReferralResult(
                referral=referral, outcome=ReferralOutcome.HANDOFF, trace=trace,
                history_ok=history_ok, handoff=record,
            ))
            self._record(referral.referral_id, "referral_completed", "handoff",
                          "processing complete (hand-off)")
            return

        try:
            note = generate_triage_note(referral, history, handoff_decision)
        except TriageBlockedError as exc:
            # Unreachable given the check above; if it ever fires, treat it exactly
            # like a hand-off rather than silently losing the referral.
            trace.append("triage_generation_blocked")
            self._record(referral.referral_id, "triage_generation_blocked", "handoff", str(exc))
            self.results.append(ReferralResult(
                referral=referral, outcome=ReferralOutcome.HANDOFF, trace=trace,
                history_ok=history_ok,
                handoff=HandoffRecord(referral.referral_id, referral.resident_ref,
                                       handoff_decision.basis or _fallback_basis(),
                                       self._context(referral, history)),
            ))
            return

        trace.append("triage_note_drafted")
        self._record(referral.referral_id, "triage_note_drafted", "success", note.narrative)
        self.results.append(ReferralResult(
            referral=referral, outcome=ReferralOutcome.AUTONOMOUS_TRIAGED, trace=trace,
            history_ok=history_ok, triage_note=note,
        ))
        self._record(referral.referral_id, "referral_completed", "success",
                      "processing complete (autonomous)")

    # -- helpers ------------------------------------------------------------

    def _context(self, referral: Referral, history: HistoryFetchResult) -> dict[str, Any]:
        """ACA-2026/1 4.2 / ACA-2026/2 3.2: carry enough context that a supervisor or
        caseworker does not have to re-read the case from the beginning."""
        ctx: dict[str, Any] = {
            "referral_id": referral.referral_id,
            "resident_ref": referral.resident_ref,
            "source": referral.source,
            "summary": referral.summary,
            "requested_action": referral.requested_action,
            "urgency": referral.urgency,
            "received_at": referral.received_at.isoformat(),
        }
        if history.outcome == HistoryFetchOutcome.OK and history.record:
            rec = history.record
            ctx["resident_status"] = rec.status
            ctx["household"] = [
                {"name": m.name, "date_of_birth": m.date_of_birth, "relationship": m.relationship}
                for m in rec.household
            ]
            ctx["recent_events"] = rec.events[-5:]
        else:
            ctx["history_retrieval_error"] = history.error or history.outcome.value
        return ctx

    def _find_result(self, referral_id: str) -> Optional[ReferralResult]:
        for r in self.results:
            if r.referral.referral_id == referral_id:
                return r
        return None

    def _summary(self) -> dict[str, int]:
        counts = {o.value: 0 for o in ReferralOutcome}
        for r in self.results:
            counts[r.outcome.value] += 1
        return counts

    def _result_to_dict(self, r: ReferralResult) -> dict:
        return {
            "referral_id": r.referral.referral_id,
            "resident_ref": r.referral.resident_ref,
            "requested_action": r.referral.requested_action,
            "outcome": r.outcome.value,
            "trace": r.trace,
            "history_ok": r.history_ok,
            "triage_note": (
                {"narrative": r.triage_note.narrative, "adopted": r.triage_note.adopted}
                if r.triage_note else None
            ),
            "escalation": (
                {"basis": r.escalation.basis.reference, "explanation": r.escalation.basis.explanation}
                if r.escalation else None
            ),
            "handoff": (
                {"basis": r.handoff.basis.reference, "explanation": r.handoff.basis.explanation}
                if r.handoff else None
            ),
        }

    def _record(self, target_id: str, action: str, outcome: str, detail: str) -> None:
        insert_audit_entry(
            self.conn, self.run_id, utc_now_iso(), action, target_id, action, outcome,
            json.dumps({"detail": detail}, default=str),
        )


def _fallback_basis():
    from app.models import PolicyBasis
    return PolicyBasis("ACA-2026/1 3.9", "drafting blocked")
