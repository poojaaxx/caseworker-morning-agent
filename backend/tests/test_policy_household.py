"""ACA-2026/1 3.9 (inserted by ACA-2026/2) household/under-18 determination.

The three official referrals whose household includes a child, verified against the
real history service data (see DECISIONS.md > "ACA-2026/2 Surprise Challenge" for the
age arithmetic, done relative to each referral's own received_at date, not wall-clock
"today" - the scenario is a fixed historical morning, 17 March 2026).
"""

from __future__ import annotations

from datetime import date

from app.models import (
    HandoffVerdict,
    HistoryFetchOutcome,
    HistoryFetchResult,
    HistoryRecord,
    HouseholdMember,
)
from app.policy import evaluate_household_for_aca_2026_2
from app.referrals import load_referral_queue

REFERENCE_DATE = date(2026, 3, 17)

EXPECTED_HANDOFF = {"RF-2026-0412": ["William Iverson"],
                     "RF-2026-0416": ["Maria Carver"],
                     "RF-2026-0418": ["Michael Crowley", "Rosa Vance"]}
EXPECTED_NOT_APPLICABLE = ["RF-2026-0413", "RF-2026-0414", "RF-2026-0415", "RF-2026-0417",
                           "RF-2026-0419", "RF-2026-0420", "RF-2026-0421", "RF-2026-0422",
                           "RF-2026-0423"]


def _fetch(history_client, resident_ref):
    return history_client.get_full_record(resident_ref)


def test_households_with_a_child_require_handoff(history_client):
    referrals = {r.referral_id: r for r in load_referral_queue()}
    for referral_id, expected_names in EXPECTED_HANDOFF.items():
        referral = referrals[referral_id]
        result = _fetch(history_client, referral.resident_ref)
        decision = evaluate_household_for_aca_2026_2(result, referral.received_date)
        assert decision.verdict == HandoffVerdict.HANDOFF_REQUIRED, referral_id
        assert decision.basis.reference.startswith("ACA-2026/1 3.9")
        for name in expected_names:
            assert name in decision.basis.explanation


def test_households_without_a_child_are_not_applicable(history_client):
    referrals = {r.referral_id: r for r in load_referral_queue()}
    for referral_id in EXPECTED_NOT_APPLICABLE:
        referral = referrals[referral_id]
        result = _fetch(history_client, referral.resident_ref)
        decision = evaluate_household_for_aca_2026_2(result, referral.received_date)
        assert decision.verdict == HandoffVerdict.NOT_APPLICABLE, referral_id


def test_exactly_three_of_twelve_require_handoff(history_client):
    referrals = load_referral_queue()
    count = 0
    for r in referrals:
        result = _fetch(history_client, r.resident_ref)
        decision = evaluate_household_for_aca_2026_2(result, r.received_date)
        if decision.verdict == HandoffVerdict.HANDOFF_REQUIRED:
            count += 1
    assert count == 3


def test_unresolvable_household_is_treated_conservatively_as_handoff():
    """ACA-2026/2 5.2: where household composition cannot be established, 3.9 is to
    be treated as applying."""
    failed_fetch = HistoryFetchResult(outcome=HistoryFetchOutcome.UNAVAILABLE,
                                       error="connection refused")
    decision = evaluate_household_for_aca_2026_2(failed_fetch, REFERENCE_DATE)
    assert decision.verdict == HandoffVerdict.HANDOFF_REQUIRED
    assert decision.household_established is False


def test_unknown_resident_is_treated_conservatively_as_handoff():
    not_found = HistoryFetchResult(outcome=HistoryFetchOutcome.NOT_FOUND, error="not found")
    decision = evaluate_household_for_aca_2026_2(not_found, REFERENCE_DATE)
    assert decision.verdict == HandoffVerdict.HANDOFF_REQUIRED


def test_malformed_date_of_birth_is_treated_conservatively_as_handoff():
    """A per-member data quality problem (ugly input), not just whole-service failure."""
    record = HistoryRecord(
        resident_ref="R-TEST", status="Active", benefit_code="X", district="X",
        award_monthly=0.0,
        household=[HouseholdMember(name="Someone", date_of_birth="not-a-date",
                                    relationship="Applicant")],
        events=[],
    )
    result = HistoryFetchResult(outcome=HistoryFetchOutcome.OK, record=record)
    decision = evaluate_household_for_aca_2026_2(result, REFERENCE_DATE)
    assert decision.verdict == HandoffVerdict.HANDOFF_REQUIRED
    assert decision.household_established is False


def test_household_with_no_members_is_not_applicable():
    record = HistoryRecord(resident_ref="R-TEST", status="Active", benefit_code="X",
                            district="X", award_monthly=0.0, household=[], events=[])
    result = HistoryFetchResult(outcome=HistoryFetchOutcome.OK, record=record)
    decision = evaluate_household_for_aca_2026_2(result, REFERENCE_DATE)
    assert decision.verdict == HandoffVerdict.NOT_APPLICABLE


def test_age_computed_relative_to_referral_received_date_not_wallclock():
    """A child who turned 18 the day before the referral was received is not
    protected; one day after is. Confirms age math, not "today"."""
    turned_18_yesterday = HouseholdMember(name="Just Adult", date_of_birth="2008-03-16",
                                           relationship="Son/daughter")
    still_17 = HouseholdMember(name="Still Minor", date_of_birth="2008-03-18",
                                relationship="Son/daughter")

    record_adult = HistoryRecord("R-A", "Active", "X", "X", 0.0, [turned_18_yesterday], [])
    decision_adult = evaluate_household_for_aca_2026_2(
        HistoryFetchResult(HistoryFetchOutcome.OK, record_adult), date(2026, 3, 17)
    )
    assert decision_adult.verdict == HandoffVerdict.NOT_APPLICABLE

    record_minor = HistoryRecord("R-B", "Active", "X", "X", 0.0, [still_17], [])
    decision_minor = evaluate_household_for_aca_2026_2(
        HistoryFetchResult(HistoryFetchOutcome.OK, record_minor), date(2026, 3, 17)
    )
    assert decision_minor.verdict == HandoffVerdict.HANDOFF_REQUIRED
