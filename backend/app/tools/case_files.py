from __future__ import annotations

from app.db import get_all_cases
from app.models import StepOutcome
from app.tools.base import GlobalTool, ToolContext, ToolResult
from app.validation import validate_case


class CaseFileUnavailableError(RuntimeError):
    """Simulates a downstream case-file storage dependency being unavailable for one
    specific case, so failure handling has something real to exercise (see
    seed_data.py, case id 9)."""


def _pull_one(case) -> dict:
    if case.simulate_failure:
        raise CaseFileUnavailableError(
            f"case file storage unavailable for case #{case.id}"
        )
    return {"id": case.id, "client_name": case.client_name}


class PullCaseFilesTool(GlobalTool):
    id = "pull_case_files"
    name = "Pull today's case files"
    reversible = True

    def execute(self, ctx: ToolContext) -> ToolResult:
        cases = [c for c in get_all_cases(ctx.conn) if c.appointment_today]

        pulled: list[dict] = []
        failed: list[dict] = []
        invalid: list[dict] = []

        for case in cases:
            try:
                pulled.append(_pull_one(case))
            except CaseFileUnavailableError as exc:
                failed.append({"id": case.id, "error": str(exc)})
                continue

            validation = validate_case(case)
            if not validation.is_valid:
                invalid.append({"id": case.id, "errors": validation.errors})
            elif validation.warnings:
                invalid.append({"id": case.id, "warnings": validation.warnings})

        has_failures = bool(failed)
        outcome = StepOutcome.PARTIAL if has_failures else StepOutcome.SUCCESS
        summary = (
            f"Pulled {len(pulled)} of {len(cases)} case file(s) for today's "
            f"appointments."
        )
        if failed:
            summary += f" {len(failed)} unavailable (dependency failure)."
        if invalid:
            summary += f" {len(invalid)} flagged by validation."

        return ToolResult(
            outcome=outcome,
            summary=summary,
            detail={"pulled": pulled, "failed": failed, "flagged": invalid},
        )
