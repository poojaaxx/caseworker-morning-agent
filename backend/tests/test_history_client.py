from __future__ import annotations

from app.history_client import HistoryServiceClient
from app.models import HistoryFetchOutcome


def test_health_check_against_real_service(history_client):
    assert history_client.health() is True


def test_fetch_known_resident_returns_full_record(history_client):
    result = history_client.get_full_record("R-20500")
    assert result.outcome == HistoryFetchOutcome.OK
    assert result.record.resident_ref == "R-20500"
    assert result.record.status == "Active"
    assert len(result.record.household) == 2
    names = {m.name for m in result.record.household}
    assert "William Iverson" in names


def test_fetch_unknown_resident_returns_not_found(history_client):
    result = history_client.get_full_record("R-DOES-NOT-EXIST")
    assert result.outcome == HistoryFetchOutcome.NOT_FOUND
    assert result.record is None
    assert result.error


def test_unreachable_service_returns_unavailable_not_a_crash():
    client = HistoryServiceClient(base_url="http://127.0.0.1:1")  # nothing listens here
    result = client.get_full_record("R-20500")
    assert result.outcome.value == "unavailable"
    assert result.record is None
    assert result.error
    client.close()


def test_household_members_include_date_of_birth_and_relationship(history_client):
    result = history_client.get_full_record("R-20500")
    member = next(m for m in result.record.household if m.name == "William Iverson")
    assert member.date_of_birth == "2021-02-26"
    assert member.relationship == "Son/daughter"
