"""Domain models shared across the orchestrator, tools, and API layer.

Kept as plain dataclasses (not pydantic) for the internal domain so the orchestrator and
tools have no framework dependency; the API layer (main.py) defines its own pydantic
request/response schemas and converts to/from these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"  # step ran to completion but one or more items within it failed
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    PENDING_APPROVAL = "pending_approval"


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass
class Case:
    id: int
    client_name: str
    status: str
    risk_flag: str
    last_contact_date: str
    compliance_deadline: str
    appointment_today: bool
    appointment_count: int
    notes: str
    simulate_failure: bool = False


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PendingApproval:
    """A single irreversible action instance awaiting an explicit human decision."""

    run_id: str
    step_id: str
    target_id: Optional[int]
    action_description: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, Optional[int]]:
        return (self.run_id, self.step_id, self.target_id)


@dataclass
class ApprovalRecord:
    run_id: str
    step_id: str
    target_id: Optional[int]
    decision: Decision
    decided_at: str
    decided_by: str


@dataclass
class StepResult:
    step_id: str
    outcome: StepOutcome
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEntry:
    run_id: str
    timestamp: str
    step_id: str
    target_id: Optional[int]
    action: str
    outcome: StepOutcome
    detail: str


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
