"""Validation rules applied to case records before a step acts on them.

This is an intentionally isolated module (a list of independent rule functions) so a
new business rule can be added without touching the orchestrator or any tool — see
DECISIONS.md > "New validation" under the Day-2 modularity guidance.

A record failing validation is never silently treated as valid: steps that read
validated_case() skip invalid records and record why, rather than crashing or guessing.
"""

from __future__ import annotations

from datetime import datetime

from app.models import Case, ValidationResult

KNOWN_STATUSES = {"active", "resolved"}


def is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def rule_client_name_present(case: Case, result: ValidationResult) -> None:
    if not case.client_name or not case.client_name.strip():
        result.errors.append("missing_client_name")


def rule_last_contact_date_valid(case: Case, result: ValidationResult) -> None:
    if not is_valid_date(case.last_contact_date):
        result.errors.append("invalid_last_contact_date")


def rule_compliance_deadline_valid(case: Case, result: ValidationResult) -> None:
    if not is_valid_date(case.compliance_deadline):
        result.errors.append("invalid_compliance_deadline")


def rule_known_status(case: Case, result: ValidationResult) -> None:
    if case.status not in KNOWN_STATUSES:
        result.errors.append(f"unknown_status:{case.status}")


def rule_no_duplicate_appointments(case: Case, result: ValidationResult) -> None:
    if case.appointment_count > 1:
        result.warnings.append("duplicate_appointment_entries")


RULES = [
    rule_client_name_present,
    rule_last_contact_date_valid,
    rule_compliance_deadline_valid,
    rule_known_status,
    rule_no_duplicate_appointments,
]


def validate_case(case: Case) -> ValidationResult:
    result = ValidationResult(is_valid=True)
    for rule in RULES:
        rule(case, result)
    result.is_valid = len(result.errors) == 0
    return result
