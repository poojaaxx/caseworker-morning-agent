from __future__ import annotations

from datetime import datetime

from app.db import get_all_cases, get_alerts, get_audit_log
from app.llm import generate_narrative
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult


class GenerateDailySummaryTool(GlobalTool):
    id = "generate_daily_summary"
    name = "Generate daily summary"
    reversible = True  # an internal artifact; can be regenerated at no cost

    def execute(self, ctx: ToolContext) -> ToolResult:
        audit = get_audit_log(ctx.conn, ctx.run_id)
        cases = get_all_cases(ctx.conn)

        def count(step_id: str, outcome: str) -> int:
            return sum(
                1 for e in audit if e["step_id"] == step_id and e["outcome"] == outcome
            )

        summary = {
            "run_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "alerts_count": len(get_alerts(ctx.conn)),
            "appointments_today": sum(1 for c in cases if c.appointment_today),
            "reminders_sent": count("send_appointment_reminders", "success"),
            "cases_closed": count("close_resolved_cases", "success"),
            "cases_escalated": count("escalate_urgent_case", "success"),
            "overdue_compliance": _overdue_count(audit),
            "items_skipped": sum(1 for e in audit if e["outcome"] in ("skipped", "rejected")),
        }

        narrative = generate_narrative(summary)

        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=narrative,
            detail={"stats": summary},
        )


def _overdue_count(audit: list[dict]) -> int:
    """flag_overdue_compliance stores its case-id list in a separate audit detail
    field rather than a simple count, so pull it out for the summary."""
    import json

    for entry in audit:
        if entry["step_id"] == "flag_overdue_compliance" and entry["outcome"] == "success":
            try:
                detail = json.loads(entry["detail"])
                return len(detail.get("overdue_case_ids", []))
            except (ValueError, KeyError, TypeError):
                return 0
    return 0
