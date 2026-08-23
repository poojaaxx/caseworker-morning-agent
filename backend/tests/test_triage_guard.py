"""Proves the drafting guard cannot be routed around, by calling triage.py directly -
not through the orchestrator. See triage.py's module docstring for why the check lives
here rather than only in orchestrator.py."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (
    HandoffDecision,
    HandoffVerdict,
    HistoryFetchOutcome,
    HistoryFetchResult,
    HistoryRecord,
    PolicyBasis,
    Referral,
)
from app.triage import TriageBlockedError, generate_triage_note


def _referral() -> Referral:
    return Referral(
        referral_id="RF-TEST", received_at=datetime(2026, 3, 17), resident_ref="R-TEST",
        source="Test", summary="x", requested_action="Review award", urgency="Standard",
    )


def _ok_history() -> HistoryFetchResult:
    record = HistoryRecord("R-TEST", "Active", "X", "X", 0.0, [], [])
    return HistoryFetchResult(HistoryFetchOutcome.OK, record)


def test_generate_triage_note_refuses_when_handoff_required():
    blocked = HandoffDecision(
        verdict=HandoffVerdict.HANDOFF_REQUIRED,
        basis=PolicyBasis("ACA-2026/1 3.9", "household includes a person under 18"),
    )
    with pytest.raises(TriageBlockedError):
        generate_triage_note(_referral(), _ok_history(), blocked)


def test_generate_triage_note_succeeds_when_not_applicable():
    allowed = HandoffDecision(verdict=HandoffVerdict.NOT_APPLICABLE)
    note = generate_triage_note(_referral(), _ok_history(), allowed)
    assert note.referral_id == "RF-TEST"
    assert note.narrative
    assert note.adopted is None  # pending caseworker decision, ACA-2026/1 2.4


def test_no_note_object_is_produced_on_the_blocked_path():
    """The function must raise, not return a note marked somehow 'blocked' - there is
    no partial/draft-for-later-adoption artifact for a protected household (ACA-2026/2
    2.2: 'not merely to its adoption... may not produce a draft note for such a case
    at all')."""
    blocked = HandoffDecision(
        verdict=HandoffVerdict.HANDOFF_REQUIRED,
        basis=PolicyBasis("ACA-2026/1 3.9", "household includes a person under 18"),
    )
    try:
        result = generate_triage_note(_referral(), _ok_history(), blocked)
    except TriageBlockedError:
        result = None
    assert result is None
