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

This file will be updated if additional AI assistance (e.g., for the Day-2 surprise
requirement) is used.
