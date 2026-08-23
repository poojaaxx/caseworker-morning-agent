from __future__ import annotations

import pytest

from app.models import RunStatus
from app.orchestrator import OrchestratorError, ReferralRunOrchestrator
from app.referrals import load_referral_queue


def test_full_run_processes_all_twelve_official_referrals(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()

    assert orchestrator.status == RunStatus.COMPLETED
    assert len(orchestrator.results) == 12
    summary = orchestrator.get_state()["summary"]
    assert summary["autonomous_triaged"] == 6
    assert summary["escalated"] == 3
    assert summary["handoff"] == 3
    assert summary["not_processed"] == 0


def test_escalating_one_referral_does_not_stop_the_queue(make_orchestrator):
    """ACA-2026/1 4.3: escalation of one referral must not prevent processing others."""
    orchestrator = make_orchestrator()
    orchestrator.run()
    # RF-2026-0415 escalates; RF-2026-0423 (later in the queue) must still be reached.
    ids_seen = {r.referral.referral_id for r in orchestrator.results}
    assert "RF-2026-0415" in ids_seen
    assert "RF-2026-0423" in ids_seen


def test_handoff_does_not_refetch_history(conn, history_client, monkeypatch):
    """ACA-2026/2 4.2 / 3.1: history already retrieved must be reused, not discarded
    and re-fetched, when establishing whether 3.9 applies."""
    calls = []
    original = history_client.get_full_record

    def counting(resident_ref):
        calls.append(resident_ref)
        return original(resident_ref)

    monkeypatch.setattr(history_client, "get_full_record", counting)

    orchestrator = ReferralRunOrchestrator(conn, "spy-run", history_client=history_client)
    orchestrator.run()

    # Exactly one history fetch per referral - never more, regardless of outcome,
    # and never for the same resident twice (each referral concerns a distinct
    # resident in the official queue).
    assert len(calls) == len(orchestrator.referrals)
    assert len(calls) == len(set(calls))


def test_handoff_preserves_already_gathered_context(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    handoff_result = next(r for r in orchestrator.results if r.referral.referral_id == "RF-2026-0412")
    assert handoff_result.handoff is not None
    assert handoff_result.handoff.context["resident_ref"] == "R-20500"
    assert "household" in handoff_result.handoff.context
    assert handoff_result.triage_note is None  # never drafted


def test_escalation_preserves_context_for_a_supervisor(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    escalated = next(r for r in orchestrator.results if r.referral.referral_id == "RF-2026-0415")
    assert escalated.escalation is not None
    assert escalated.escalation.context["requested_action"] == "Suspend assistance pending investigation"
    assert escalated.triage_note is None  # never drafted, not even partially


def test_hard_distinction_between_escalation_and_handoff(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    results_by_id = {r.referral.referral_id: r for r in orchestrator.results}

    # RF-2026-0415: out-of-authority action -> ESCALATED, not HANDOFF.
    assert results_by_id["RF-2026-0415"].outcome.value == "escalated"
    assert results_by_id["RF-2026-0415"].handoff is None

    # RF-2026-0412: under-18 household, in-authority action -> HANDOFF, not ESCALATED.
    assert results_by_id["RF-2026-0412"].outcome.value == "handoff"
    assert results_by_id["RF-2026-0412"].escalation is None


# -- adoption -----------------------------------------------------------------------

def test_adopt_note_approve(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    autonomous = next(r for r in orchestrator.results if r.outcome.value == "autonomous_triaged")
    orchestrator.adopt_note(autonomous.referral.referral_id, "approve")
    assert autonomous.triage_note.adopted is True


def test_adopt_note_reject(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    autonomous = next(r for r in orchestrator.results if r.outcome.value == "autonomous_triaged")
    orchestrator.adopt_note(autonomous.referral.referral_id, "reject")
    assert autonomous.triage_note.adopted is False


@pytest.mark.parametrize("bad", ["yes", "", None, "APPROVE", 1, "approve please"])
def test_adopt_note_rejects_ambiguous_decision(make_orchestrator, bad):
    orchestrator = make_orchestrator()
    orchestrator.run()
    autonomous = next(r for r in orchestrator.results if r.outcome.value == "autonomous_triaged")
    with pytest.raises(OrchestratorError):
        orchestrator.adopt_note(autonomous.referral.referral_id, bad)
    assert autonomous.triage_note.adopted is None  # untouched


def test_adopt_note_cannot_be_resubmitted(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    autonomous = next(r for r in orchestrator.results if r.outcome.value == "autonomous_triaged")
    orchestrator.adopt_note(autonomous.referral.referral_id, "approve")
    with pytest.raises(OrchestratorError):
        orchestrator.adopt_note(autonomous.referral.referral_id, "reject")
    assert autonomous.triage_note.adopted is True  # first decision stands


def test_adopt_note_fails_for_referral_with_no_draft(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    escalated = next(r for r in orchestrator.results if r.outcome.value == "escalated")
    with pytest.raises(OrchestratorError, match="no drafted triage note"):
        orchestrator.adopt_note(escalated.referral.referral_id, "approve")


def test_adopt_note_fails_for_unknown_referral(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    with pytest.raises(OrchestratorError):
        orchestrator.adopt_note("RF-DOES-NOT-EXIST", "approve")


# -- cancellation -------------------------------------------------------------------

def test_cancel_after_partial_processing_preserves_earlier_results(conn, history_client):
    referrals = load_referral_queue()
    orchestrator = ReferralRunOrchestrator(conn, "cancel-run", history_client=history_client,
                                            referrals=referrals)
    # Process the first 3 manually, then cancel.
    for _ in range(3):
        referral = orchestrator._queue.pop(0)
        orchestrator._process_referral(referral)

    processed_ids_before = {r.referral.referral_id for r in orchestrator.results}
    orchestrator.cancel()

    assert orchestrator.status == RunStatus.CANCELLED
    processed_after = [r for r in orchestrator.results if r.referral.referral_id in processed_ids_before]
    assert len(processed_after) == 3  # not discarded, not re-processed
    not_processed = [r for r in orchestrator.results if r.outcome.value == "not_processed"]
    assert len(not_processed) == len(referrals) - 3


def test_cannot_cancel_a_completed_run(make_orchestrator):
    orchestrator = make_orchestrator()
    orchestrator.run()
    with pytest.raises(OrchestratorError):
        orchestrator.cancel()


def test_cannot_cancel_twice(conn, history_client):
    orchestrator = ReferralRunOrchestrator(conn, "cancel-run-2", history_client=history_client)
    orchestrator.cancel()
    with pytest.raises(OrchestratorError):
        orchestrator.cancel()


def test_unexpected_error_on_one_referral_does_not_lose_the_others(conn, history_client, monkeypatch):
    """'One referral failing should not lose the work already done on the others'
    (official problem statement, 'if you have time'). Simulates a bug in policy
    evaluation for one referral and confirms the run still completes with every other
    referral processed and recorded, and the failure itself is visible, not silent."""
    import app.orchestrator as orchestrator_module

    referrals = load_referral_queue()
    original = orchestrator_module.evaluate_requested_action
    boom_id = referrals[3].referral_id

    def flaky(referral):
        if referral.referral_id == boom_id:
            raise RuntimeError("simulated bug in policy evaluation")
        return original(referral)

    monkeypatch.setattr(orchestrator_module, "evaluate_requested_action", flaky)

    orchestrator = ReferralRunOrchestrator(conn, "flaky-run", history_client=history_client,
                                            referrals=referrals)
    orchestrator.run()

    assert orchestrator.status == RunStatus.COMPLETED
    assert len(orchestrator.results) == len(referrals)  # nothing lost
    failed = next(r for r in orchestrator.results if r.referral.referral_id == boom_id)
    assert failed.outcome.value == "failed"
    other_ids = {r.referral.referral_id for r in orchestrator.results} - {boom_id}
    assert other_ids == {r.referral_id for r in referrals if r.referral_id != boom_id}


def test_empty_referral_queue_completes_cleanly(conn, history_client):
    orchestrator = ReferralRunOrchestrator(conn, "empty-run", history_client=history_client, referrals=[])
    orchestrator.run()
    assert orchestrator.status == RunStatus.COMPLETED
    assert orchestrator.results == []
