# Decisions

Maintained throughout development, not written at the end. Phase 1 (before the official
data pack was available) and Phase 2 (after it, including the Day-2 amendment) are both
kept below — the corrections are as informative as the original decisions.

## Initial Project Direction (Phase 1)

**Context:** The workspace was empty at the start of Phase 1 — no official Problem 5
data pack was present, only the general problem statement. We built a generic
caseworker-morning workflow (alerts, calendar, case files, reminders, closing/escalating
cases) as a **documented assumption**, explicitly flagged as such, with an architecture
designed to be easy to replace once real requirements arrived.

**Outcome:** That assumption was superseded once the official data pack and Day-2
amendment were supplied. See "Corrections to Initial Assumptions" below. What survived
the correction: the explicit-decision primitive (`guardrails.py`, unchanged), the
FastAPI/SQLite/pytest technology choices, the audit-log pattern, cancellation, and the
general discipline of frequent real commits and an honest `DECISIONS.md`. What did not
survive: literally everything about the invented 9-step workflow, its mock data, and
its tools — none of it resembled the real Problem 5.

## Corrections to Initial Assumptions

The official data pack (`data-pack/`) and the Day-2 amendment were supplied together.
Reading the official README made one thing immediately clear: the real problem is
narrower and more specific than Phase 1's generic assumption. The real "morning
sequence" is exactly three steps — read the overnight referrals, pull each resident's
history, draft a triage note — over a fixed 12-referral queue, governed by a written
authority policy (ACA-2026/1), with at least one referral deliberately outside the
agent's authority.

Specifically corrected:
- **The workflow.** Phase 1's alerts/calendar/reminders/close-case/escalate-case
  sequence is gone. The real workflow is the three-step sequence above, driven by
  policy evaluation rather than a fixed list of "morning routine" actions.
- **The data.** Phase 1's invented `Case` model and mock seed data are gone. The
  official 12-referral queue and the official Resident History API (both unmodified,
  in `data-pack/`) are the only data sources.
- **The approval model.** Phase 1 modeled "propose an irreversible action, human
  approves, agent executes it." The real policy has no such flow for out-of-authority
  actions — see "Structural Safety" below for why this is a stronger guarantee, not a
  downgrade.
- **The UI.** Phase 1 treated the frontend as core deliverable infrastructure. The
  official problem statement explicitly says a UI is not required and interface
  quality is not assessed. The frontend was updated (not rebuilt at the same level of
  investment) and a plain stdout CLI trace (`run_cli.py`) was added as the primary,
  simplest way to satisfy the traceability requirement.

## Official Data Pack Integration

Files under `data-pack/` are byte-identical copies of the supplied originals (verified
with `diff` before commit) — nothing in them was edited. They were relocated from the
hackathon's raw extraction folders (`5 1/`, `5 - Surprise Challenge/` — messy names,
`__MACOSX`/`.DS_Store` cruft, a `.docx`) into a clean, tracked `data-pack/` directory;
the raw folders themselves are gitignored, not committed.

The official `.docx` problem statement (not machine-readable) was extracted via its
underlying zip/XML and read in full — see "The floor," below, which quotes it directly.
It is more specific than the paraphrase we initially had at the start of Phase 2, and
several of its details materially changed priorities (a UI is explicitly not required;
"interface quality is not assessed"; the hard-approval-gate requirement is about
irreversible actions never executing, not about a UI approval dialog).

## Architecture Decisions

**The pipeline, per referral** (`orchestrator.py`):

```
referral_loaded -> history_retrieved -> policy_evaluated
    -> [ESCALATION_REQUIRED] -> escalation_created -> referral_completed
    -> [else] household_evaluated
          -> [HANDOFF_REQUIRED, ACA-2026/2 3.9] -> handoff_created -> referral_completed
          -> [else]                             -> triage_note_drafted -> referral_completed
```

Escalating or handing off one referral never stops the loop — the next referral is
always attempted (ACA-2026/1 §4.3, ACA-2026/2 §4.2).

**Decision:** Policy evaluation is a pure function of the referral's own text
(`requested_action`, `summary`) and, separately, the household data returned by the
history service — never of `referral_id` or `resident_ref`. See `policy.py`; there is
no `if referral_id == ...` anywhere in this codebase.

**Decision:** History is retrieved exactly once per referral (a single
`GET /residents/<ref>` call returns the full record — status, household, events — so
there is no reason to call the service two or three times per referral). The same
`HistoryFetchResult` is reused for the escalation/hand-off context and for the ACA-
2026/2 household check. Verified by
`tests/test_orchestrator.py::test_handoff_does_not_refetch_history`, which spies on
call count.

**Decision:** Run state (results so far, current position in the queue) is in-memory
only, exactly as in Phase 1; the audit log persists to SQLite. Same tradeoff, same
reasoning as Phase 1 — see "Known Limitations."

## Technology Decisions

Unchanged from Phase 1's reasoning (Python/FastAPI/SQLite, no unnecessary
infrastructure) with one addition: **httpx** as the HTTP client for the official
history service (already a transitive dependency via FastAPI's TestClient in Phase 1,
so no new dependency was actually introduced by adding it to `requirements.txt`
directly).

The official history service (`data-pack/services/history_service.py`) is stdlib-only,
per the organizers' own design — we run it unmodified, as a genuinely separate process
communicated with over HTTP, rather than importing its data directly. This was a
deliberate choice: importing `_history_data.json` directly would have been faster to
wire up, but it would not exercise the actual "official data pack" as a real dependency
with real failure modes (unreachable service, unknown resident, malformed response) —
and those failure modes are exactly what ACA-2026/2 §5.2's conservative rule exists for.
Treating the service as a real HTTP dependency, including in tests (see "Testing"), is
what makes the "history service cannot be established" pathway a tested reality rather
than a hypothetical.

## Policy as Data

The official problem statement says, in its "if you have time" section: *"Make the
policy the source of truth rather than the code. If the authority boundary is expressed
as data the agent reads, changing the policy does not mean changing the program."* and
*"the discipline that pays is not hard-coding the rules of the policy into the flow of
the agent."*

`policy.py`'s classification of a requested action against ACA-2026/1 §3 is driven by
`policy_rules.json` — a table of keyword-to-section mappings, verb lists, and a
change-verb/noun rule — not by per-referral or per-section `if` statements. Adding a
new restricted-action keyword, or a new category entirely, is a data edit to that file;
`policy.py`'s code does not need to change. This is our own structured translation of
the prose policy (`authority-policy.md` remains the authoritative document a human
reads); we were honest with ourselves that a JSON keyword table is not a general NLU
system — see "Known Limitations."

The household/ACA-2026/2 check (`evaluate_household_for_aca_2026_2`) is a smaller,
more literal translation of §3.9/§5.1/§5.2 (age arithmetic against the referral's own
`received_at` date, not wall-clock time — the scenario is a fixed historical morning,
17 March 2026, and using real "today" would make the demo's behavior silently drift
as time passes).

## Agent Design / Workflow

The full referral-by-referral classification, verified against the real official data
(`tests/test_policy_actions.py`, `tests/test_policy_household.py`):

| Referral | Requested action | Verdict | Basis |
|---|---|---|---|
| RF-2026-0412 | Review award | HAND-OFF | household includes William Iverson (age 5) |
| RF-2026-0413 | Record change of address | autonomous | — |
| RF-2026-0414 | Review award | autonomous | — |
| RF-2026-0415 | Suspend assistance pending investigation | **ESCALATION** | §3.2 |
| RF-2026-0416 | Review household composition | HAND-OFF | household includes Maria Carver (age 3) |
| RF-2026-0417 | Draft explanatory note | autonomous | — |
| RF-2026-0418 | Review award | HAND-OFF | household includes two children |
| RF-2026-0419 | Record income change | autonomous | — |
| RF-2026-0420 | Flag for contact attempt | autonomous | — |
| RF-2026-0421 | Review household composition | autonomous | — |
| RF-2026-0422 | Draft triage note for supervisor | **ESCALATION** | §3.2 (see below) |
| RF-2026-0423 | Update payment details | **ESCALATION** | §3.4 |

**RF-2026-0422 is the deliberate trap.** Its `requested_action` field reads "Draft
triage note for supervisor" — on its face, that is exactly what §2.4 permits, and a
classifier that only looks at `requested_action` would wave it through as autonomous.
Its `summary` says "Panel decision received. Award to be reinstated from date of
termination." — the substance is an award **reinstatement**, squarely §3.2, regardless
of how mildly the `requested_action` field phrases it. The official README warns about
exactly this: *"do not assume that the referrals which matter announce themselves...
A routine-looking request can engage section 3 just as squarely as a dramatic one."*
`evaluate_requested_action` therefore scans `summary` as well as `requested_action` for
the restricted-keyword rules (not for the softer autonomous-verb/change-verb rules,
which are deliberately requested_action-only to avoid false positives — see next
paragraph) — this is what catches RF-2026-0422 correctly.

**A false positive we caught and fixed before committing:** an early version of the
change-verb rule scanned `summary` too, and RF-2026-0418's summary ("resident asks
whether **award changes**") nearly misclassified as a §3.1 match on the substring
"chang-". That referral is a question, not a change request — no one is asking the
agent to change anything. We narrowed the change-verb/noun rule to `requested_action`
only, keeping the broader summary scan restricted to the small set of unambiguous
strong keywords (`suspend`, `terminat`, `reinstat`, `payment details`, etc.) that are
very unlikely to appear as false positives in ordinary case-note prose. This is
recorded here rather than silently fixed, per the honesty requirement.

## Hand-Off vs Escalation

These are deliberately different states, per ACA-2026/2 §3.3: *"An escalation says the
Department must decide whether this may happen at all. A hand-off says this is ordinary
casework that a person must do."*

- **Escalation** (`EscalationRecord`, `ReferralOutcome.ESCALATED`): the referral's
  requested action itself is outside the agent's authority. Nothing about the action is
  performed, prepared, or drafted.
- **Hand-off** (`HandoffRecord`, `ReferralOutcome.HANDOFF`): the requested action is
  ordinary, in-authority casework — the *only* reason the agent stops is that ACA-
  2026/2 §3.9 prohibits *drafting* for this household. The agent still reads the
  referral and retrieves history/household (§3.1 of the amendment permits and requires
  this, to determine whether 3.9 even applies).

Kept as genuinely separate dataclasses, separate `ReferralOutcome` values, separate
audit-log actions (`escalation_created` vs `handoff_created`), and separate UI
badges/CLI labels — never merged into one generic "human required" state. Verified by
`tests/test_orchestrator.py::test_hard_distinction_between_escalation_and_handoff`.

In the official 12-referral dataset, no referral triggers both conditions at once (the
three escalation-required referrals' households contain no one under 18), so precedence
never had to be exercised on real data. The code still has a defined, tested order:
requested-action policy is evaluated first; §3.9 is only evaluated for referrals that
passed that check, since an escalated referral is never drafted regardless of household
composition, so §3.9 is moot for it. Documented here as a design decision made for
robustness/extensibility, not one the dataset forced.

## ACA-2026/2 Surprise Challenge (Day-2)

**What changed:** Amendment ACA-2026/2 inserts §3.9 into ACA-2026/1's section 3:
drafting a triage note is itself prohibited (not just its adoption) for a referral
concerning a household that includes a person under 18. It also requires: (a) reading/
retrieving/determining household composition remains permitted, since it's how §3.9 is
established in the first place; (b) a hand-off preserving whatever was already
gathered; (c) this hand-off be structurally distinguishable from an escalation; (d) the
amendment applies to work already in progress, and that work must not be discarded or
the run restarted.

**How it was integrated:** Every one of those requirements maps onto an existing
extension point rather than a new architecture:

- New restricted-drafting rule → `evaluate_household_for_aca_2026_2` in `policy.py`
  (the module already built to hold policy evaluation).
- New "the agent must refuse to draft" behavior → `triage.py`'s guard, the one and only
  function that produces triage-note text.
- New outcome / new record type → `ReferralOutcome.HANDOFF` and `HandoffRecord`,
  siblings of the escalation types already in `models.py`.
- New pipeline branch → one `if` in `orchestrator.py`'s existing per-referral pipeline,
  reusing the same history fetch, the same audit-log helper, the same trace-list
  pattern already used for escalation.

No existing module was rewritten to fit this in. This is the concrete demonstration
that "problem-solving" (architecture that absorbs a Day-2 change) is not a claim made
in the abstract — it's the actual diff for this feature, and it's small.

**Age determination:** from the household composition the history service returns
(`date_of_birth` fields), computed relative to each referral's own `received_at` date —
never from referral wording, never hardcoded per resident. Verified against the three
real affected referrals (William Iverson, Maria Carver, Michael Crowley + Rosa Vance)
and against synthetic edge cases (turns 18 the day before vs. the day of/after the
reference date; malformed date of birth; empty household).

**Conservative default (§5.2):** if household composition cannot be established at all
— history service unreachable, resident not found, or a household member's date of
birth is unparseable — §3.9 is treated as applying. This is not the same code path as
"no children found"; both `HistoryFetchOutcome.NOT_FOUND`/`UNAVAILABLE` and a per-member
unparseable DOB are distinguished explicitly in `policy.py` and both resolve to
`HANDOFF_REQUIRED`, never silently to "safe to draft."

## Partial Workflow Preservation

ACA-2026/2 §4.1/§4.2 requires that work already done on a referral survive the
amendment coming into force, and that the run not restart from the beginning. In this
implementation the amendment was known from the start of coding, not literally
encountered mid-run during development, so compliance is demonstrated structurally
rather than narrated as a live event:

1. History/household data is fetched exactly once per referral and reused for both the
   §3.9 determination and the hand-off record's context — nothing fetched is discarded,
   nothing is fetched twice (tested, see "Architecture Decisions" above).
2. Referrals are processed as an ordered queue where each referral's result is recorded
   immediately and independently. Detecting §3.9 on referral N never touches, re-reads,
   or reprocesses referrals 1..N-1 — verified by
   `test_cancel_after_partial_processing_preserves_earlier_results`, which processes
   three referrals, cancels, and confirms all three results are untouched and the
   remaining nine are marked `not_processed` (recorded, not silently dropped).
3. If a run is stopped and later a new run starts, it starts from the full queue again
   by design (there is no partially-adopted state to resume mid-referral) — but nothing
   about an *individual referral's* processing is ever re-done partway through; each
   referral's pipeline run is atomic from the orchestrator's point of view.

## Structural Safety

*What this agent is structurally incapable of doing without a human, and how we know —
not what we told it not to do.*

**There is no function anywhere in this codebase that suspends, terminates, or
reinstates an award; changes payment/bank/card details; sends a communication to a
resident or third party; discloses resident information outside the Department; or
records a finding of fact about a resident's conduct.** Grep the codebase for
`suspend`, `terminate`, `disclose`, `send_communication`, `record_finding` as an
*action* (as opposed to a keyword the policy evaluator matches in referral text) and
you will not find one. These are not capabilities that exist behind a permission check
that could, in principle, be bypassed by a bug, a prompt-injection, or a determined
caller — they were simply never built. "A human must do it" is not a policy this code
enforces; it is a fact about what code exists. That is a stronger guarantee than an
approval gate can ever provide, because an approval gate is a check that a capability
respects, and a check can have a bug. An absent capability cannot.

**Drafting a triage note is a real capability this agent has** (§2.4 explicitly
permits it), and ACA-2026/2 §3.9 conditionally restricts it. That restriction *is*
enforced by a check — `triage.py`'s `generate_triage_note()` — because unlike the
section-3 actions above, this capability genuinely exists and needs a gate. The
guarantee here is narrower but still concrete: `generate_triage_note()` is the only
function in the codebase that produces triage-note text (`grep -rn "narrative ="` or
`grep -rn generate_triage_narrative` finds exactly one caller, inside the guard); the
guard is the first thing the function does, before any note text — including the
optional LLM call — is generated; there is no parameter, flag, or second code path that
skips it. `tests/test_triage_guard.py` calls this function directly, not through the
orchestrator, and confirms both that it raises for a protected household and that no
note object is produced on that path (not a note flagged "blocked" — no note at all,
per ACA-2026/2 §2.2: *"the restriction... applies to the drafting of the note itself...
An assistant may not produce a draft note for such a case at all"*).

**What is not structurally guaranteed:** the *classification* that decides which path a
referral takes (`policy.py`) is a keyword/rule table, and a rule table can be wrong for
text it wasn't written to anticipate. ACA-2026/1 §6.1's conservative default (treat
ambiguity as though it falls within section 3) is our mitigation for that: an
unrecognized `requested_action` escalates rather than silently drafting. This is a
judgement call, not a structural proof, and we say so plainly rather than overselling
it as equivalent to the "no such function exists" argument above.

## Data Handling

The referral queue and history data are read from `data-pack/`, unmodified, and never
mutated by this application — there is no code path that writes back to
`referral-queue.json` or `_history_data.json`. `referrals.py` validates every record on
load (required fields present, `received_at` parseable) and fails the whole run with a
clear error rather than silently skipping or inventing a malformed record — the
official queue is the given input, not something to be defensive about beyond
detecting whether it's actually the file we expect.

## Error Handling

- History service unreachable, resident not found, or a malformed response: caught in
  `history_client.py`, surfaced as a typed outcome (`NOT_FOUND` / `UNAVAILABLE`), never
  raised as an uncaught exception into the orchestrator.
- Escalation-required referrals are classified from referral text alone, so a history
  service outage does not change their outcome — verified by running the CLI against a
  queue with the service stopped (see the "Failure behavior" section of `README.md`):
  the three escalations are unaffected; the remaining nine conservatively hand off.
- Malformed/missing referral queue file: fails fast with `ReferralQueueError`, not a
  silently-empty or partially-loaded queue.
- Malformed adoption input (missing/ambiguous decision): rejected by the same
  `guardrails.parse_decision` used in Phase 1, at the API boundary (400) and at the
  orchestrator level (`OrchestratorError`) — never treated as approval.
- Cancelling: see "Partial Workflow Preservation."

## Testing

73 tests (`pytest`, run from `backend/`), replacing Phase 1's suite, which tested a
now-superseded assumption (see "Corrections to Initial Assumptions" — those tests were
deleted, not silently left to fail; `guardrails.py`'s own logic is unchanged and its
tests were re-verified as still valid before being folded into the new suite's
coverage). Covers: the official 12-referral queue including malformed-input handling;
the *real, unmodified* history service (started as a subprocess fixture on a disposable
port, not mocked) including unknown-resident and unreachable-service paths; the policy
evaluator against all 12 real referrals plus synthetic edge cases; the ACA-2026/2
household check against all 12 real referrals plus conservative-default cases; the
triage guard called directly; the full orchestrator pipeline (escalation/hand-off don't
stop the queue, hand-off doesn't re-fetch, cancellation preserves partial work); note
adoption; and the same behaviors again at the HTTP API layer.

## Features Rejected

- **LLM-based policy classification.** Rejected for the same reason as Phase 1: the
  official problem statement itself says "this is not a problem about deciding what to
  do" and rewards a keyword/data-driven evaluator whose behavior can be pinned down and
  tested exactly, not a model call whose classification could vary run to run for the
  one part of this system where a wrong answer means a resident's benefit action either
  wrongly escalates or wrongly doesn't.
- **A UI-first demo.** Explicitly not required by the official problem statement,
  which also states interface quality is not assessed. Investment went into the CLI
  trace, the policy engine, and tests instead; the frontend was updated to a working,
  clear-enough state and no further.
- **Full NLU / a real rules engine for policy matching.** A keyword table
  (`policy_rules.json`) is not a substitute for reading natural language the way a
  person or an LLM would. We chose it anyway because it is exactly predictable,
  testable, and auditable — see "Structural Safety"'s honest caveat about this.

## Features Cut Due to Time

- A persisted, resumable run state machine (unchanged from Phase 1's cut — still
  in-memory only).
- Handling referral types or policy categories beyond what's in the official 12 and
  `authority-policy.md` (explicitly not required by the problem statement).
- Any real external integration for "sending" a communication or updating payment
  details — these remain escalation-only, by design (see Structural Safety), not a
  simulated capability.

## Known Limitations

- In-memory run state: an in-progress run does not survive a backend restart (nothing
  already recorded is lost — see "Partial Workflow Preservation").
- `policy_rules.json` is a keyword table, not general language understanding; a
  restricted-action phrased in genuinely novel language could be missed by the
  affirmative rules — mitigated, not solved, by the §6.1 conservative default.
- Single-process; not built for concurrent multi-caseworker load.
- The frontend is intentionally minimal, per the official problem's own guidance that
  UI is not required and not assessed for this problem.

## What the Solution Does Not Do

- Does not perform, simulate, or provide any code path for suspending/terminating/
  reinstating an award, changing payment or bank/card details, sending any
  communication, disclosing resident information, or recording a finding of fact about
  a resident's conduct. All of these are escalation-only.
- Does not use an LLM for any decision that affects which path a referral takes
  (escalate / hand off / draft) — only, optionally, for phrasing the text of an
  already-authorized draft.
- Does not persist run state across a backend restart.
- Does not handle referrals or policy categories outside the official data pack.

## Clean Clone Verification (Phase 2)

Performed after all of the above, from a fresh `git clone` into an empty temp
directory, on a machine that already had Python 3.11 and git: `git clone` → `python -m
venv .venv` → `pip install -r requirements.txt` → started
`data-pack/services/history_service.py` in a separate terminal → `pytest` (**73
passed**, ~137s) → `python run_cli.py` (all 12 referrals processed: 6 autonomous, 3
escalated, 3 hand-off, matching the table above exactly) → `uvicorn app.main:app` →
`POST /api/runs` via curl returned the same summary. No undocumented steps were
needed. (`pytest` does not require the manually-started service — it starts its own
disposable instance of the same unmodified script on a different port; the manual
instance was only needed for `run_cli.py`/`uvicorn`, exactly as README.md documents.)

## What We Would Improve First

- Replace the keyword-table policy classifier with something that can flag its own
  low-confidence matches for human review, rather than only the binary conservative
  default.
- Persist orchestrator run state so an in-progress run survives a restart.
- A richer supervisor-facing escalation queue (the current API/CLI surfaces the record;
  a real deployment would want a proper queue a supervisor works from).
