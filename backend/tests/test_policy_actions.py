"""ACA-2026/1 section 3/4/6.1 classification, driven by policy_rules.json.

The parametrized case below is the master correctness test: every referral in the
official 12-referral queue, checked against the expected verdict derived by hand from
authority-policy.md (see DECISIONS.md > "Official Data Pack Integration" for the
referral-by-referral reasoning, including RF-2026-0422 - phrased as an innocuous
"draft triage note for supervisor" but substantively an award reinstatement under 3.2,
which is why the evaluator reads the summary text too, not just requested_action).
"""

from __future__ import annotations

import pytest

from app.models import ActionVerdict, Referral
from app.policy import evaluate_requested_action
from app.referrals import load_referral_queue
from datetime import datetime

EXPECTED = {
    "RF-2026-0412": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0413": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0414": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0415": (ActionVerdict.ESCALATION_REQUIRED, "ACA-2026/1 3.2"),
    "RF-2026-0416": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0417": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0418": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0419": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0420": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0421": (ActionVerdict.AUTONOMOUS, None),
    "RF-2026-0422": (ActionVerdict.ESCALATION_REQUIRED, "ACA-2026/1 3.2"),
    "RF-2026-0423": (ActionVerdict.ESCALATION_REQUIRED, "ACA-2026/1 3.4"),
}


@pytest.mark.parametrize("referral_id", list(EXPECTED))
def test_official_referral_classified_correctly(referral_id):
    referral = next(r for r in load_referral_queue() if r.referral_id == referral_id)
    decision = evaluate_requested_action(referral)
    expected_verdict, expected_basis = EXPECTED[referral_id]
    assert decision.verdict == expected_verdict
    if expected_basis:
        assert decision.basis is not None
        assert decision.basis.reference == expected_basis


def test_exactly_three_of_twelve_require_escalation():
    referrals = load_referral_queue()
    decisions = [evaluate_requested_action(r) for r in referrals]
    escalated = [d for d in decisions if d.verdict == ActionVerdict.ESCALATION_REQUIRED]
    assert len(escalated) == 3


def _referral(requested_action: str, summary: str = "") -> Referral:
    return Referral(
        referral_id="RF-TEST", received_at=datetime(2026, 3, 17), resident_ref="R-TEST",
        source="Test", summary=summary, requested_action=requested_action, urgency="Standard",
    )


def test_ambiguous_action_defaults_conservatively_to_escalation():
    """ACA-2026/1 6.1: where it is unclear whether an action falls within section 3,
    treat it as though it does. Not exercised by the official 12, so tested directly."""
    decision = evaluate_requested_action(_referral("Do something unusual with the file"))
    assert decision.verdict == ActionVerdict.ESCALATION_REQUIRED
    assert decision.basis.reference == "ACA-2026/1 6.1"


def test_change_award_amount_requires_escalation():
    decision = evaluate_requested_action(_referral("Change award amount"))
    assert decision.verdict == ActionVerdict.ESCALATION_REQUIRED
    assert decision.basis.reference == "ACA-2026/1 3.1"


def test_send_communication_to_resident_requires_escalation():
    decision = evaluate_requested_action(
        _referral("Notify resident of decision", "Send a letter to the resident directly.")
    )
    assert decision.verdict == ActionVerdict.ESCALATION_REQUIRED
    assert decision.basis.reference == "ACA-2026/1 3.5"


def test_drafting_is_not_confused_with_sending():
    """'draft' is explicitly excluded from the communication rule - drafting a note
    is always permitted (2.4) regardless of who it is eventually meant for."""
    decision = evaluate_requested_action(_referral("Draft a note to send to the resident later"))
    assert decision.verdict == ActionVerdict.AUTONOMOUS


def test_review_is_not_a_change():
    decision = evaluate_requested_action(_referral("Review award eligibility"))
    assert decision.verdict == ActionVerdict.AUTONOMOUS
