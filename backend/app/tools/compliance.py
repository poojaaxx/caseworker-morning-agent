from __future__ import annotations

from datetime import datetime

from app.db import get_all_cases
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult
from app.validation import is_valid_date


class FlagOverdueComplianceTool(GlobalTool):
    id = "flag_overdue_compliance"
    name = "Flag overdue compliance tasks"
    reversible = True

    def execute(self, ctx: ToolContext) -> ToolResult:
        today = datetime.utcnow().date()
        cases = get_all_cases(ctx.conn)

        overdue: list[int] = []
        unparseable: list[int] = []
        for case in cases:
            if not is_valid_date(case.compliance_deadline):
                unparseable.append(case.id)
                continue
            deadline = datetime.strptime(case.compliance_deadline, "%Y-%m-%d").date()
            if deadline < today:
                overdue.append(case.id)

        summary = f"{len(overdue)} case(s) have an overdue compliance deadline."
        if unparseable:
            summary += (
                f" {len(unparseable)} case(s) skipped - unparseable deadline."
            )

        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=summary,
            detail={"overdue_case_ids": overdue, "unparseable_case_ids": unparseable},
        )
