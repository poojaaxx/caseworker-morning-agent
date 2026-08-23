#!/usr/bin/env python3
"""Runs the full referral queue and prints a readable execution trace to stdout.

Per the official problem statement: "Command-line delivery is fine. Interface quality
is not assessed on this problem" and "A readable trace on stdout or in a log file is
fine." This script is the simplest, most direct way to see the agent's full run and
satisfies the floor's traceability requirement (ACA-2026/1 5.1) on its own, independent
of the API/frontend.

Usage:
    python run_cli.py [--history-url http://127.0.0.1:8083]

Requires the official history service to be running separately - see README.md.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from app.db import get_connection, init_db
from app.history_client import HistoryServiceClient
from app.orchestrator import ReferralRunOrchestrator
from app.referrals import ReferralQueueError

OUTCOME_LABELS = {
    "autonomous_triaged": "AUTONOMOUS - TRIAGE NOTE DRAFTED",
    "escalated": "ESCALATION REQUIRED",
    "handoff": "HUMAN HAND-OFF (ACA-2026/2)",
    "not_processed": "NOT PROCESSED (run cancelled first)",
    "failed": "UNEXPECTED ERROR",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-url", default=None,
                         help="Base URL of the resident history API (default: "
                              "$HISTORY_SERVICE_URL or http://127.0.0.1:8083)")
    args = parser.parse_args()

    print("=" * 78)
    print("Calder County - Automated Casework Assistant")
    print("Processing overnight referral queue (ACA-2026/1 / ACA-2026/2)")
    print("=" * 78)

    client = HistoryServiceClient(args.history_url) if args.history_url else HistoryServiceClient()
    if not client.health():
        print(
            f"\nWARNING: resident history API not reachable at {client.base_url}.\n"
            "Start it first:  python data-pack/services/history_service.py --port 8083\n"
            "Continuing anyway - referrals will conservatively hand off where "
            "household composition cannot be established (ACA-2026/2 5.2).\n"
        )

    conn = get_connection(Path(tempfile.mktemp(suffix=".db")))
    init_db(conn, reset=True)

    try:
        orchestrator = ReferralRunOrchestrator(conn, run_id="cli-run", history_client=client)
    except ReferralQueueError as exc:
        print(f"FATAL: could not load referral queue: {exc}", file=sys.stderr)
        return 1

    orchestrator.run()
    state = orchestrator.get_state()
    orchestrator.close()

    for r in state["results"]:
        print(f"\n[{r['referral_id']}]  resident {r['resident_ref']}")
        print(f"  requested action : {r['requested_action']}")
        print(f"  outcome          : {OUTCOME_LABELS.get(r['outcome'], r['outcome'])}")
        print(f"  trace            : {' -> '.join(r['trace'])}")
        if r["triage_note"]:
            print(f"  triage note      : {r['triage_note']['narrative']}")
        if r["escalation"]:
            print(f"  policy basis     : {r['escalation']['basis']}")
            print(f"  reason           : {r['escalation']['explanation']}")
        if r["handoff"]:
            print(f"  policy basis     : {r['handoff']['basis']}")
            print(f"  reason           : {r['handoff']['explanation']}")
            print("  TRIAGE NOTE NOT GENERATED")

    print("\n" + "=" * 78)
    print(f"Run status: {state['status']}")
    print(f"Summary   : {state['summary']}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
