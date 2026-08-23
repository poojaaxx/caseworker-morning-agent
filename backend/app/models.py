"""Domain models for the referral-triage agent (Problem 5, official data pack).

Kept as plain dataclasses (not pydantic) so the orchestrator/policy/history-client layers
have no framework dependency; the API layer (main.py) defines its own pydantic
request/response schemas and converts to/from these.

Superseded Phase-1 models (Case, per-action PendingApproval/StepOutcome pause state)
have been removed - see DECISIONS.md > "Corrections to Initial Assumptions." What
remains here (RunStatus, Decision, ApprovalRecord, AuditEntry, utc_now_iso,
ValidationResult) is genuinely domain-agnostic and is reused unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass
class ApprovalRecord:
    """A recorded human decision for one specific action instance. Reused unchanged
    from Phase 1 (see guardrails.py) - this shape is domain-agnostic."""

    run_id: str
    step_id: str
    target_id: Optional[str]
    decision: Decision
    decided_at: str
    decided_by: str


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AuditEntry:
    run_id: str
    timestamp: str
    step_id: str
    target_id: Optional[str]
    action: str
    outcome: str
    detail: str


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# -- Official data pack domain --------------------------------------------------

@dataclass
class Referral:
    referral_id: str
    received_at: datetime
    resident_ref: str
    source: str
    summary: str
    requested_action: str
    urgency: str

    @property
    def received_date(self) -> date:
        return self.received_at.date()


@dataclass
class HouseholdMember:
    name: str
    date_of_birth: Optional[str]  # "YYYY-MM-DD" or None/malformed if data quality issue
    relationship: str


@dataclass
class HistoryRecord:
    resident_ref: str
    status: str
    benefit_code: str
    district: str
    award_monthly: float
    household: list[HouseholdMember]
    events: list[dict]


class HistoryFetchOutcome(str, Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"  # connection/timeout/unexpected-response failure


@dataclass
class HistoryFetchResult:
    outcome: HistoryFetchOutcome
    record: Optional[HistoryRecord] = None
    error: Optional[str] = None


# -- Policy (ACA-2026/1 + ACA-2026/2) -------------------------------------------

@dataclass
class PolicyBasis:
    reference: str  # e.g. "ACA-2026/1 3.2"
    explanation: str


class ActionVerdict(str, Enum):
    AUTONOMOUS = "autonomous"
    ESCALATION_REQUIRED = "escalation_required"


@dataclass
class ActionDecision:
    verdict: ActionVerdict
    basis: Optional[PolicyBasis] = None


class HandoffVerdict(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    HANDOFF_REQUIRED = "handoff_required"


@dataclass
class HandoffDecision:
    verdict: HandoffVerdict
    basis: Optional[PolicyBasis] = None
    household_established: bool = True


# -- Per-referral outcome --------------------------------------------------------

class ReferralOutcome(str, Enum):
    AUTONOMOUS_TRIAGED = "autonomous_triaged"
    ESCALATED = "escalated"
    HANDOFF = "handoff"
    NOT_PROCESSED = "not_processed"  # run cancelled before this referral was reached


@dataclass
class TriageNote:
    referral_id: str
    resident_ref: str
    narrative: str
    adopted: Optional[bool] = None  # None = pending caseworker decision (ACA-2026/1 2.4)


@dataclass
class EscalationRecord:
    referral_id: str
    resident_ref: str
    basis: PolicyBasis
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class HandoffRecord:
    referral_id: str
    resident_ref: str
    basis: PolicyBasis
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReferralResult:
    referral: Referral
    outcome: ReferralOutcome
    trace: list[str] = field(default_factory=list)
    history_ok: bool = True
    triage_note: Optional[TriageNote] = None
    escalation: Optional[EscalationRecord] = None
    handoff: Optional[HandoffRecord] = None
