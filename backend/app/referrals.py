"""Loads the official overnight referral queue (ACA-2026/1 2.1: "Read a referral from
the overnight queue").

The queue is a fixed data file supplied with the problem, not something this
application owns or mutates - see data-pack/README.md. We read it, we do not modify it,
and we do not invent additional referrals.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import Referral

DEFAULT_QUEUE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data-pack" / "referral-queue.json"
)

REQUIRED_FIELDS = (
    "referral_id", "received_at", "resident_ref", "source", "summary",
    "requested_action", "urgency",
)


class ReferralQueueError(ValueError):
    """Raised when the referral queue file is missing, malformed, or a record is
    missing a required field - never silently skipped or guessed at."""


def load_referral_queue(path: Optional[Path] = None) -> list[Referral]:
    queue_path = path or DEFAULT_QUEUE_PATH
    if not queue_path.exists():
        raise ReferralQueueError(f"referral queue file not found: {queue_path}")

    try:
        raw = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReferralQueueError(f"referral queue file is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise ReferralQueueError("referral queue file must contain a JSON array")

    referrals: list[Referral] = []
    for i, record in enumerate(raw):
        if not isinstance(record, dict):
            raise ReferralQueueError(f"referral queue entry {i} is not a JSON object")
        missing = [f for f in REQUIRED_FIELDS if f not in record]
        if missing:
            raise ReferralQueueError(
                f"referral queue entry {i} is missing required field(s): {missing}"
            )
        try:
            received_at = datetime.fromisoformat(record["received_at"])
        except ValueError as exc:
            raise ReferralQueueError(
                f"referral {record.get('referral_id', i)!r} has an unparseable "
                f"received_at: {record['received_at']!r}"
            ) from exc

        referrals.append(Referral(
            referral_id=record["referral_id"],
            received_at=received_at,
            resident_ref=record["resident_ref"],
            source=record["source"],
            summary=record["summary"],
            requested_action=record["requested_action"],
            urgency=record["urgency"],
        ))

    return referrals
