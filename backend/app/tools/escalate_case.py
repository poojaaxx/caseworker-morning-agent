from __future__ import annotations

from app.db import get_all_cases, set_case_status
from app.models import Case, StepOutcome
from app.tools.base import PerCaseTool, ToolContext, ToolResult


class EscalateUrgentCaseTool(PerCaseTool):
    id = "escalate_urgent_case"
    name = "Escalate urgent case to supervisor"
    reversible = False  # notifies a party outside this system

    def get_targets(self, ctx: ToolContext) -> list[Case]:
        return [c for c in get_all_cases(ctx.conn) if c.risk_flag == "urgent"]

    def describe_action(self, ctx: ToolContext, case: Case) -> tuple[str, str]:
        description = (
            f"Escalate case #{case.id} ({case.client_name}) to a supervisor as a "
            f"high-risk case requiring immediate attention."
        )
        reason = (
            "Escalation notifies a supervisor outside this system and cannot be "
            "un-sent; a human must confirm the escalation is warranted."
        )
        return description, reason

    def execute_one(self, ctx: ToolContext, case: Case) -> ToolResult:
        set_case_status(ctx.conn, case.id, "escalated")
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"Case #{case.id} ({case.client_name}) escalated to supervisor.",
            detail={"case_id": case.id, "new_status": "escalated"},
        )
