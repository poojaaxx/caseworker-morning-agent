from __future__ import annotations

from app.db import get_all_cases
from app.models import Case, StepOutcome
from app.tools.base import PerCaseTool, ToolContext, ToolResult


class SendRemindersTool(PerCaseTool):
    id = "send_appointment_reminders"
    name = "Send appointment reminders"
    reversible = False  # a message sent to a client cannot be unsent

    def get_targets(self, ctx: ToolContext) -> list[Case]:
        return [c for c in get_all_cases(ctx.conn) if c.appointment_today]

    def describe_action(self, ctx: ToolContext, case: Case) -> tuple[str, str]:
        description = (
            f"Send an appointment reminder message to {case.client_name!r} "
            f"(case #{case.id}) for today's scheduled visit."
        )
        reason = (
            "This sends a real message to a client. Once delivered it cannot be "
            "recalled or unsent, so a human must confirm it should go out."
        )
        return description, reason

    def execute_one(self, ctx: ToolContext, case: Case) -> ToolResult:
        # Simulated send: a real integration would call an SMS/email provider here,
        # behind this same tool interface (see DECISIONS.md > What We Would Improve First).
        return ToolResult(
            outcome=StepOutcome.SUCCESS,
            summary=f"Reminder sent to {case.client_name} (case #{case.id}).",
            detail={"case_id": case.id, "channel": "sms"},
        )
