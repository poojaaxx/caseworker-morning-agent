from __future__ import annotations

from app.models import Case
from app.validation import validate_case


def _case(**overrides) -> Case:
    base = dict(
        id=1, client_name="Test Client", status="active", risk_flag="none",
        last_contact_date="2026-08-20", compliance_deadline="2026-09-01",
        appointment_today=False, appointment_count=0, notes="",
    )
    base.update(overrides)
    return Case(**base)


def test_valid_case_passes():
    result = validate_case(_case())
    assert result.is_valid
    assert result.errors == []


def test_missing_client_name_is_invalid():
    result = validate_case(_case(client_name=""))
    assert not result.is_valid
    assert "missing_client_name" in result.errors


def test_whitespace_only_client_name_is_invalid():
    result = validate_case(_case(client_name="   "))
    assert not result.is_valid
    assert "missing_client_name" in result.errors


def test_invalid_last_contact_date_is_invalid():
    result = validate_case(_case(last_contact_date="not-a-date"))
    assert not result.is_valid
    assert "invalid_last_contact_date" in result.errors


def test_invalid_compliance_deadline_is_invalid():
    result = validate_case(_case(compliance_deadline="13/45/2026"))
    assert not result.is_valid
    assert "invalid_compliance_deadline" in result.errors


def test_unknown_status_is_invalid():
    result = validate_case(_case(status="pending_transfer"))
    assert not result.is_valid
    assert any(e.startswith("unknown_status") for e in result.errors)


def test_duplicate_appointments_is_a_warning_not_an_error():
    result = validate_case(_case(appointment_count=2))
    assert result.is_valid  # still valid - it's a warning, not blocking
    assert "duplicate_appointment_entries" in result.warnings


def test_multiple_errors_are_all_reported():
    result = validate_case(_case(client_name="", status="bogus", last_contact_date="???"))
    assert not result.is_valid
    assert len(result.errors) == 3
