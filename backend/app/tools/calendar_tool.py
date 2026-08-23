from __future__ import annotations

from app.db import get_all_cases
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult


class CheckCalendarTool(GlobalTool):
    id = "check_calendar"
    name = "Check today's calendar"
    reversible = True

    def execute(self, ctx: ToolContext) -> ToolResult:
        cases = get_all_cases(ctx.conn)
        todays = [c for c in cases if c.appointment_today]
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"{len(todays)} appointment(s) scheduled today.",
            detail={"case_ids": [c.id for c in todays]},
        )
