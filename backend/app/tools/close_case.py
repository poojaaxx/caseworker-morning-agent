from __future__ import annotations

from app.db import get_all_cases, set_case_status
from app.models import Case, StepOutcome
from app.tools.base import PerCaseTool, ToolContext, ToolResult


class CloseResolvedCasesTool(PerCaseTool):
    id = "close_resolved_cases"
    name = "Close resolved cases"
    reversible = False  # a closed case has downstream reporting/funding effects

    def get_targets(self, ctx: ToolContext) -> list[Case]:
        return [c for c in get_all_cases(ctx.conn) if c.status == "resolved"]

    def describe_action(self, ctx: ToolContext, case: Case) -> tuple[str, str]:
        description = (
            f"Close case #{case.id} ({case.client_name}) - status will change from "
            f"'resolved' to 'closed'."
        )
        reason = (
            "Closing a case is a significant status change with downstream "
            "reporting/funding effects and is not meant to be casually undone."
        )
        return description, reason

    def execute_one(self, ctx: ToolContext, case: Case) -> ToolResult:
        set_case_status(ctx.conn, case.id, "closed")
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"Case #{case.id} ({case.client_name}) closed.",
            detail={"case_id": case.id, "new_status": "closed"},
        )
