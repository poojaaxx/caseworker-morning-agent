from __future__ import annotations

from app.db import get_alerts
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult


class CheckAlertsTool(GlobalTool):
    id = "check_alerts"
    name = "Check overnight alerts"
    reversible = True

    def execute(self, ctx: ToolContext) -> ToolResult:
        alerts = get_alerts(ctx.conn)
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"{len(alerts)} overnight alert(s) found.",
            detail={"alerts": alerts},
        )
