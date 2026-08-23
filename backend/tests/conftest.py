from __future__ import annotations

import os

# Must happen before any `app.*` module is imported anywhere in the test session -
# app.history_client.DEFAULT_BASE_URL is a module-level constant read from this env var
# at import time. conftest.py is always imported by pytest before test modules are
# collected, so setting it here (not inside a fixture, which would run too late)
# guarantees every default-constructed HistoryServiceClient in the app points at the
# disposable test instance started below, not at some developer's manually-started one.
TEST_HISTORY_PORT = 8183
os.environ["HISTORY_SERVICE_URL"] = f"http://127.0.0.1:{TEST_HISTORY_PORT}"

import pathlib
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from app.db import get_connection, init_db
from app.history_client import HistoryServiceClient
from app.orchestrator import ReferralRunOrchestrator

HISTORY_SERVICE_SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "data-pack" / "services" / "history_service.py"
)


@pytest.fixture(scope="session", autouse=True)
def _history_service():
    """Runs the real, unmodified official history_service.py for the whole test
    session, on a disposable port. Tests exercise the actual official service and
    data, not a mock - see DECISIONS.md > "Official Data Pack Integration"."""
    proc = subprocess.Popen(
        [sys.executable, str(HISTORY_SERVICE_SCRIPT), "--port", str(TEST_HISTORY_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{TEST_HISTORY_PORT}"
    deadline = time.time() + 15
    ready = False
    with httpx.Client(timeout=1.0) as probe:
        while time.time() < deadline:
            try:
                if probe.get(f"{base_url}/health").status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    if not ready:
        proc.terminate()
        raise RuntimeError("official history service did not start in time for tests")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def conn():
    path = pathlib.Path(tempfile.mktemp(suffix=".db"))
    connection = get_connection(path)
    init_db(connection, reset=True)
    yield connection
    connection.close()
    path.unlink(missing_ok=True)


@pytest.fixture
def history_client(_history_service):
    client = HistoryServiceClient(base_url=_history_service)
    yield client
    client.close()


@pytest.fixture
def make_orchestrator(conn, history_client):
    made: list[ReferralRunOrchestrator] = []

    def _make(run_id: str = "test-run", referrals=None) -> ReferralRunOrchestrator:
        o = ReferralRunOrchestrator(conn, run_id, history_client=history_client, referrals=referrals)
        made.append(o)
        return o

    yield _make


@pytest.fixture
def client(conn, _history_service, monkeypatch):
    from app import main as main_module
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "_conn", conn)
    main_module.RUNS.clear()
    return TestClient(main_module.app)
