"""Tool interface.

Adding a new action to the caseworker's morning means writing one new Tool subclass and
registering it in workflow.py - nothing else needs to change (see DECISIONS.md > "New
tool" under Day-2 modularity guidance).

Two shapes of tool exist:

  GlobalTool   - acts once for the whole run (e.g. "check calendar"). Implement execute().
  PerCaseTool  - acts once per matching case (e.g. "close resolved cases", one approval
                 per case). Implement get_targets() and execute_one().

Both declare `reversible: bool`. The orchestrator is the only thing that reads this
flag and it is the sole authority on whether an approval gate applies - see guardrails.py.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models import Case, StepOutcome


@dataclass
class ToolContext:
    conn: sqlite3.Connection
    run_id: str
    caseworker: str = "demo-caseworker"


@dataclass
class ToolResult:
    outcome: StepOutcome
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)


class GlobalTool(ABC):
    id: str
    name: str
    reversible: bool = True
    per_target: bool = False

    @abstractmethod
    def execute(self, ctx: ToolContext) -> ToolResult:
        ...


class PerCaseTool(ABC):
    id: str
    name: str
    reversible: bool = False
    per_target: bool = True

    @abstractmethod
    def get_targets(self, ctx: ToolContext) -> list[Case]:
        """Cases this step would act on, recomputed fresh from the DB each call."""

    @abstractmethod
    def describe_action(self, ctx: ToolContext, case: Case) -> tuple[str, str]:
        """Return (action_description, reason) shown to the human before approval."""

    @abstractmethod
    def execute_one(self, ctx: ToolContext, case: Case) -> ToolResult:
        ...
