from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from app.referrals import ReferralQueueError, load_referral_queue


def test_official_queue_loads_all_twelve_referrals():
    referrals = load_referral_queue()
    assert len(referrals) == 12
    assert len({r.referral_id for r in referrals}) == 12  # all unique


def test_official_queue_fields_parsed():
    referrals = load_referral_queue()
    first = next(r for r in referrals if r.referral_id == "RF-2026-0412")
    assert first.resident_ref == "R-20500"
    assert first.source == "Housing Options"
    assert first.requested_action == "Review award"
    assert first.urgency == "Standard"
    assert first.received_at.year == 2026


def test_missing_queue_file_raises_clear_error():
    with pytest.raises(ReferralQueueError, match="not found"):
        load_referral_queue(pathlib.Path("/does/not/exist.json"))


def test_malformed_json_raises_clear_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ReferralQueueError, match="not valid JSON"):
        load_referral_queue(bad_file)


def test_queue_must_be_a_list(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(ReferralQueueError, match="JSON array"):
        load_referral_queue(bad_file)


def test_missing_required_field_raises_clear_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    record = {
        "referral_id": "RF-TEST-1", "received_at": "2026-03-17T00:00:00",
        "resident_ref": "R-1", "source": "Test",
        # "summary" missing
        "requested_action": "Review award", "urgency": "Standard",
    }
    bad_file.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(ReferralQueueError, match="missing required field"):
        load_referral_queue(bad_file)


def test_unparseable_received_at_raises_clear_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    record = {
        "referral_id": "RF-TEST-1", "received_at": "not-a-date",
        "resident_ref": "R-1", "source": "Test", "summary": "x",
        "requested_action": "Review award", "urgency": "Standard",
    }
    bad_file.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(ReferralQueueError, match="unparseable"):
        load_referral_queue(bad_file)
