"""HTTP client for the official Resident History API (data-pack/services/history_service.py).

ACA-2026/1 2.2 permits an assistant to retrieve a resident's history, household
composition, and case events on its own. This client does exactly that and nothing
else - it has no method that could change anything on the other end, because the
official service does not expose one (it is read-only, GET-only).

Failure handling (ACA-2026/2 5.2: "Where household composition cannot be established,
[the drafting restriction] is to be treated as applying"): any failure to reach the
service, a 404 for an unknown resident, or a malformed response is surfaced as
HistoryFetchOutcome.NOT_FOUND / UNAVAILABLE - never silently treated as "no household"
or "empty household". Callers (policy.py) must treat both as "cannot be established".
"""

from __future__ import annotations

import os
import time

import httpx

from app.models import HistoryFetchOutcome, HistoryFetchResult, HistoryRecord, HouseholdMember

DEFAULT_BASE_URL = os.environ.get("HISTORY_SERVICE_URL", "http://127.0.0.1:8083")

# Free-tier hosting (see render.yaml) puts the history service to sleep after
# inactivity and rate-limits bursts of traffic while it cold-starts - both surface as
# either a connection error or a 429/5xx response, not as the resident data being
# genuinely unavailable. Retrying a few times with backoff rides out that window
# instead of letting one cold-start turn into a false HANDOFF (ACA-2026/2 5.2 treats
# any UNAVAILABLE outcome as "household composition cannot be established").
_RETRY_STATUS_CODES = {429, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.4


class HistoryServiceClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0):
        base_url = base_url.rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            # Render's blueprint `fromService` linking (see render.yaml) hands services
            # a bare "host:port" for private-network calls, with no scheme - tolerate
            # that here rather than require every caller to prepend one. Explicit
            # http(s):// URLs (local dev, tests) are passed through unchanged.
            base_url = f"http://{base_url}"
        self.base_url = base_url
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def health(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _get_with_retry(self, url: str) -> httpx.Response | None:
        """GETs `url`, retrying transient failures (connection errors, 429, 5xx) with
        backoff. Returns None if every attempt was transient failure; a non-2xx/3xx
        response is still returned as-is on the final attempt so callers keep handling
        e.g. 404 exactly as before."""
        last_exc: httpx.HTTPError | None = None
        resp: httpx.Response | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self._client.get(url)
                last_exc = None
            except httpx.HTTPError as exc:
                last_exc = exc
                resp = None

            is_last_attempt = attempt == _RETRY_ATTEMPTS - 1
            transient = last_exc is not None or (resp is not None and resp.status_code in _RETRY_STATUS_CODES)
            if not transient or is_last_attempt:
                break
            time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))

        if last_exc is not None:
            raise last_exc
        return resp

    def get_full_record(self, resident_ref: str) -> HistoryFetchResult:
        try:
            resp = self._get_with_retry(f"{self.base_url}/residents/{resident_ref}")
        except httpx.HTTPError as exc:
            return HistoryFetchResult(
                outcome=HistoryFetchOutcome.UNAVAILABLE,
                error=f"could not reach history service: {exc}",
            )

        if resp.status_code == 404:
            return HistoryFetchResult(outcome=HistoryFetchOutcome.NOT_FOUND,
                                       error=f"resident {resident_ref!r} not found")

        if resp.status_code != 200:
            return HistoryFetchResult(
                outcome=HistoryFetchOutcome.UNAVAILABLE,
                error=f"history service returned unexpected status {resp.status_code}",
            )

        try:
            data = resp.json()
            household = [
                HouseholdMember(
                    name=m.get("name", ""),
                    date_of_birth=m.get("date_of_birth"),
                    relationship=m.get("relationship", ""),
                )
                for m in data["household"]
            ]
            record = HistoryRecord(
                resident_ref=data["resident_ref"],
                status=data.get("status", ""),
                benefit_code=data.get("benefit_code", ""),
                district=data.get("district", ""),
                award_monthly=data.get("award_monthly", 0.0),
                household=household,
                events=data.get("events", []),
            )
        except (ValueError, KeyError, TypeError) as exc:
            return HistoryFetchResult(
                outcome=HistoryFetchOutcome.UNAVAILABLE,
                error=f"malformed response from history service: {exc}",
            )

        return HistoryFetchResult(outcome=HistoryFetchOutcome.OK, record=record)
