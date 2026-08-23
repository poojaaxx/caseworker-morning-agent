from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.db import get_connection, init_db
from app.orchestrator import Orchestrator


@pytest.fixture
def conn():
    """A fresh, seeded SQLite connection backed by a throwaway temp file, isolated
    from the real data/caseworker.db used by the running app."""
    path = pathlib.Path(tempfile.mktemp(suffix=".db"))
    connection = get_connection(path)
    init_db(connection, reset=True)
    yield connection
    connection.close()
    path.unlink(missing_ok=True)


@pytest.fixture
def make_orchestrator(conn):
    def _make(run_id: str = "test-run") -> Orchestrator:
        return Orchestrator(conn, run_id)

    return _make


@pytest.fixture
def client(conn, monkeypatch):
    """A FastAPI TestClient wired to the isolated `conn` fixture instead of the app's
    real module-level connection/db file, with a clean in-memory run registry."""
    from app import main as main_module
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "_conn", conn)
    main_module.RUNS.clear()
    return TestClient(main_module.app)
