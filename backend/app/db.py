"""SQLite persistence: the audit log.

ACA-2026/1 5.1: "Every action taken by an assistant must be recorded in a form that
allows a supervisor to reconstruct, after the fact, what was done, in what order, on
what information, and what was declined." This table, plus the in-memory trace/result
objects built by orchestrator.py, is how that requirement is met. Referral data itself
is not owned/mutated here - it is read fresh from data-pack/referral-queue.json on each
run (see referrals.py); there is nothing to persist for it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "caseworker.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    step_id TEXT NOT NULL,
    target_id TEXT,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        conn.executescript("DROP TABLE IF EXISTS audit_log;")
    conn.executescript(_SCHEMA)
    conn.commit()


def insert_audit_entry(
    conn: sqlite3.Connection,
    run_id: str,
    timestamp: str,
    step_id: str,
    target_id: Optional[str],
    action: str,
    outcome: str,
    detail: str,
) -> None:
    conn.execute(
        """INSERT INTO audit_log (run_id, timestamp, step_id, target_id, action,
                                   outcome, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, timestamp, step_id, target_id, action, outcome, detail),
    )
    conn.commit()


def get_audit_log(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? ORDER BY seq", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]
