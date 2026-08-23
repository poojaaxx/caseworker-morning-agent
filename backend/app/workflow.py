"""The caseworker's morning workflow: a fixed, ordered list of steps.

This is the single place that defines "the same sequence of clicks." To add a Day-2
step, append (or insert) a WorkflowStep here and implement its tool in
app/tools/ - the orchestrator does not need to change (see DECISIONS.md > Day-2
Surprise Requirement / modularity guidance).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tools.alerts import CheckAlertsTool
from app.tools.base import GlobalTool, PerCaseTool
from app.tools.calendar_tool import CheckCalendarTool
from app.tools.case_files import PullCaseFilesTool
from app.tools.close_case import CloseResolvedCasesTool
from app.tools.compliance import FlagOverdueComplianceTool
from app.tools.escalate_case import EscalateUrgentCaseTool
from app.tools.queue import TriageQueueTool
from app.tools.reminders import SendRemindersTool
from app.tools.summary import GenerateDailySummaryTool


@dataclass
class WorkflowStep:
    tool: GlobalTool | PerCaseTool


WORKFLOW: list[WorkflowStep] = [
    WorkflowStep(CheckAlertsTool()),
    WorkflowStep(TriageQueueTool()),
    WorkflowStep(CheckCalendarTool()),
    WorkflowStep(PullCaseFilesTool()),
    WorkflowStep(SendRemindersTool()),
    WorkflowStep(FlagOverdueComplianceTool()),
    WorkflowStep(CloseResolvedCasesTool()),
    WorkflowStep(EscalateUrgentCaseTool()),
    WorkflowStep(GenerateDailySummaryTool()),
]
