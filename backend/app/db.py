"""SQLite persistence: case records and the audit log.

Run/approval state itself is kept in-memory by the orchestrator (see DECISIONS.md >
Architecture Decisions for why); this module only persists things that must survive a
restart and be inspectable afterwards: the case data and every audit entry.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from app.models import Case
from app.seed_data import SEED_ALERTS, SEED_CASES

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "caseworker.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY,
    client_name TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_flag TEXT NOT NULL,
    last_contact_date TEXT NOT NULL,
    compliance_deadline TEXT NOT NULL,
    appointment_today INTEGER NOT NULL,
    appointment_count INTEGER NOT NULL,
    notes TEXT NOT NULL,
    simulate_failure INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    step_id TEXT NOT NULL,
    target_id INTEGER,
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
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, reset: bool = False) -> None:
    """Create schema if missing, and seed case data if the cases table is empty.

    reset=True drops and reseeds everything; used by tests to guarantee a clean,
    known starting state for every test run.
    """
    if reset:
        conn.executescript(
            "DROP TABLE IF EXISTS cases; DROP TABLE IF EXISTS alerts; "
            "DROP TABLE IF EXISTS audit_log;"
        )
    conn.executescript(_SCHEMA)

    count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    if count == 0:
        conn.executemany(
            """INSERT INTO cases
               (id, client_name, status, risk_flag, last_contact_date,
                compliance_deadline, appointment_today, appointment_count, notes,
                simulate_failure)
               VALUES (:id, :client_name, :status, :risk_flag, :last_contact_date,
                       :compliance_deadline, :appointment_today, :appointment_count,
                       :notes, :simulate_failure)""",
            [
                {**c, "appointment_today": int(c["appointment_today"]),
                 "simulate_failure": int(c["simulate_failure"])}
                for c in SEED_CASES
            ],
        )
        conn.executemany(
            "INSERT INTO alerts (id, case_id, type, message) "
            "VALUES (:id, :case_id, :type, :message)",
            SEED_ALERTS,
        )
        conn.commit()


def row_to_case(row: sqlite3.Row) -> Case:
    return Case(
        id=row["id"],
        client_name=row["client_name"],
        status=row["status"],
        risk_flag=row["risk_flag"],
        last_contact_date=row["last_contact_date"],
        compliance_deadline=row["compliance_deadline"],
        appointment_today=bool(row["appointment_today"]),
        appointment_count=row["appointment_count"],
        notes=row["notes"],
        simulate_failure=bool(row["simulate_failure"]),
    )


def get_all_cases(conn: sqlite3.Connection) -> list[Case]:
    rows = conn.execute("SELECT * FROM cases ORDER BY id").fetchall()
    return [row_to_case(r) for r in rows]


def get_case(conn: sqlite3.Connection, case_id: int) -> Optional[Case]:
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return row_to_case(row) if row else None


def get_alerts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM alerts ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def set_case_status(conn: sqlite3.Connection, case_id: int, status: str) -> None:
    conn.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
    conn.commit()


def insert_audit_entry(
    conn: sqlite3.Connection,
    run_id: str,
    timestamp: str,
    step_id: str,
    target_id: Optional[int],
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
