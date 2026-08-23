# AI Usage

This project was built for Brite Spark 2026 (Problem 5 — The Caseworker's Morning) with
assistance from Claude (Anthropic), used as a pair-programming/software-engineering
assistant throughout development.

Areas AI assistance was used:

- Project scaffolding and folder structure
- Backend implementation (FastAPI orchestrator, tools, guardrail/approval logic, SQLite
  data access)
- Frontend implementation (HTML/JS demo UI)
- Test generation (pytest suite covering workflow, guardrails, validation, failure paths)
- Debugging and refactoring during development
- Documentation drafting (README.md, DECISIONS.md, this file)
- Reviewing implementation approaches and tradeoffs (e.g., where to enforce the approval
  gate, how to keep the architecture modular for an unknown Day-2 requirement)

All AI-suggested code was reviewed, run, and adapted by the developer during development;
nothing generated was committed without being read and tested first. No AI model output
(LLM or otherwise) is permitted to directly trigger an irreversible action in this
system — see DECISIONS.md ("Human Approval / Guardrails" and "LLM Usage") for how that
boundary is enforced in code.

## Phase 2 (official data pack + Day-2 surprise)

The same AI assistance (Claude, Anthropic) continued for Phase 2: reading and analyzing
the official data pack (`data-pack/authority-policy.md`, `referral-queue.json`, the
history service) and the Day-2 amendment (`ACA-2026/2`) supplied for this problem;
deriving the referral-by-referral policy classification by hand against the policy text
(recorded in `DECISIONS.md`); implementing the policy evaluator, history-service client,
triage-drafting guard, and rewritten orchestrator; rewriting the test suite against the
real official history service; and updating all three required documents.

All classification decisions (which referrals escalate, which hand off) were verified
programmatically against the real official service and data before being written up in
`DECISIONS.md` and encoded as test assertions — they were not asserted from the AI's
reasoning alone without checking them against the actual data pack. One reasoning
mistake was caught and corrected during development (an over-broad keyword rule nearly
misclassified RF-2026-0418 as a policy-3.1 match by scanning free text for "chang-" and
matching "award changes" in a question rather than a request) — see `DECISIONS.md` →
"Agent Design / Workflow" for the specific fix, kept in the record rather than silently
corrected.

This file will be updated further if additional AI assistance is used.
