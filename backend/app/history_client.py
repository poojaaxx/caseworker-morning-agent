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

import httpx

from app.models import HistoryFetchOutcome, HistoryFetchResult, HistoryRecord, HouseholdMember

DEFAULT_BASE_URL = os.environ.get("HISTORY_SERVICE_URL", "http://127.0.0.1:8083")


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

    def get_full_record(self, resident_ref: str) -> HistoryFetchResult:
        try:
            resp = self._client.get(f"{self.base_url}/residents/{resident_ref}")
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
