from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.models import utc_now_iso

_MILLISECOND_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_utc_now_iso_ends_with_z():
    assert utc_now_iso().endswith("Z")


def test_utc_now_iso_has_millisecond_precision():
    value = utc_now_iso()
    assert _MILLISECOND_UTC_TIMESTAMP.match(value), value


def test_utc_now_iso_is_a_real_utc_timestamp():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utc_now_iso()
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    parsed = datetime.fromisoformat(value[:-1])  # strip the trailing "Z"
    # isoformat(timespec="milliseconds") floors microseconds to the millisecond, so a
    # bound captured with full microsecond precision can read later than the floored
    # value even though real time moved forward - allow a 1ms margin either side.
    margin = timedelta(milliseconds=1)
    assert before - margin <= parsed <= after + margin
