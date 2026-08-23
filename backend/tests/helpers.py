from __future__ import annotations

from app.orchestrator import Orchestrator


def run_to_completion(orchestrator: Orchestrator, decisions: dict | None = None,
                       default: str = "approve", max_steps: int = 50) -> Orchestrator:
    """Start a run and answer every pending approval, defaulting to `default` unless
    `decisions` maps (step_id, target_id) -> "approve"/"reject" for a specific action."""
    decisions = decisions or {}
    orchestrator.start()
    guard = 0
    while orchestrator.status.value == "awaiting_approval" and guard < max_steps:
        guard += 1
        pending = orchestrator.pending
        key = (pending.step_id, pending.target_id)
        orchestrator.submit_approval(pending.step_id, pending.target_id,
                                      decisions.get(key, default))
    return orchestrator
