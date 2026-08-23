from __future__ import annotations

from app.db import get_all_cases
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult


def _priority(case) -> tuple:
    # Lower sorts first. Urgent risk beats everything, then anything with today's
    # appointment, then the rest by id for a stable, predictable order.
    return (0 if case.risk_flag == "urgent" else 1, 0 if case.appointment_today else 1, case.id)


class TriageQueueTool(GlobalTool):
    id = "triage_queue"
    name = "Triage case queue"
    reversible = True

    def execute(self, ctx: ToolContext) -> ToolResult:
        cases = get_all_cases(ctx.conn)
        ordered = sorted(cases, key=_priority)
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"Queue triaged: {len(ordered)} case(s) ordered by priority.",
            detail={"order": [c.id for c in ordered]},
        )
