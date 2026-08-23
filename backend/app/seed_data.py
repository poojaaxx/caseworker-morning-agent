"""Mock case-management data used to seed SQLite on first run.

Deliberately includes messy/ugly records (see DECISIONS.md > Data Handling) so the
validation and error-handling layers have something real to catch:

  id 1  - clean record, resolved, candidate for closure
  id 2  - clean record, urgent risk flag, candidate for escalation
  id 3  - clean record, has an appointment today, candidate for a reminder
  id 4  - missing client_name
  id 5  - unparseable last_contact_date
  id 6  - compliance_deadline already in the past
  id 7  - duplicate appointment entries (appointment_count > 1)
  id 8  - unknown/unexpected status value
  id 9  - marked to simulate a downstream tool failure (dependency unavailable)
  id 10 - clean, ordinary active case with no action needed today
"""

from __future__ import annotations

SEED_CASES: list[dict] = [
    {
        "id": 1,
        "client_name": "Maria Alvarez",
        "status": "resolved",
        "risk_flag": "none",
        "last_contact_date": "2026-08-18",
        "compliance_deadline": "2026-09-01",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "Housing plan completed; ready to close.",
        "simulate_failure": False,
    },
    {
        "id": 2,
        "client_name": "Devon Price",
        "status": "active",
        "risk_flag": "urgent",
        "last_contact_date": "2026-08-22",
        "compliance_deadline": "2026-08-30",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "Client reported an unsafe home situation overnight.",
        "simulate_failure": False,
    },
    {
        "id": 3,
        "client_name": "Ha-eun Kim",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-20",
        "compliance_deadline": "2026-09-10",
        "appointment_today": True,
        "appointment_count": 1,
        "notes": "9:30am check-in scheduled.",
        "simulate_failure": False,
    },
    {
        "id": 4,
        "client_name": "",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-19",
        "compliance_deadline": "2026-09-05",
        "appointment_today": True,
        "appointment_count": 1,
        "notes": "Intake record incomplete - client name never entered.",
        "simulate_failure": False,
    },
    {
        "id": 5,
        "client_name": "Sam O'Neill",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "not-a-date",
        "compliance_deadline": "2026-09-12",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "Legacy record migrated from paper file; date unreadable.",
        "simulate_failure": False,
    },
    {
        "id": 6,
        "client_name": "Priya Natarajan",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-15",
        "compliance_deadline": "2026-07-01",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "Quarterly review overdue.",
        "simulate_failure": False,
    },
    {
        "id": 7,
        "client_name": "Jordan Lee",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-21",
        "compliance_deadline": "2026-09-08",
        "appointment_today": True,
        "appointment_count": 2,
        "notes": "Two appointment entries created by a scheduling glitch.",
        "simulate_failure": False,
    },
    {
        "id": 8,
        "client_name": "Ana Costa",
        "status": "pending_transfer",
        "risk_flag": "none",
        "last_contact_date": "2026-08-10",
        "compliance_deadline": "2026-09-20",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "Status value not recognized by this system's workflow.",
        "simulate_failure": False,
    },
    {
        "id": 9,
        "client_name": "Tomasz Nowak",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-21",
        "compliance_deadline": "2026-09-15",
        "appointment_today": True,
        "appointment_count": 1,
        "notes": "Case file storage simulates an unavailable dependency for this case.",
        "simulate_failure": True,
    },
    {
        "id": 10,
        "client_name": "Grace Okafor",
        "status": "active",
        "risk_flag": "none",
        "last_contact_date": "2026-08-22",
        "compliance_deadline": "2026-10-01",
        "appointment_today": False,
        "appointment_count": 0,
        "notes": "No action required today.",
        "simulate_failure": False,
    },
]

SEED_ALERTS: list[dict] = [
    {
        "id": 1,
        "case_id": 2,
        "type": "urgent_risk",
        "message": "Overnight hotline report flagged for case #2 (Devon Price).",
    },
    {
        "id": 2,
        "case_id": 4,
        "type": "new_referral",
        "message": "New referral received overnight, intake incomplete (case #4).",
    },
]
