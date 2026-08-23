"""Policy evaluator: ACA-2026/1 (authority-policy.md) + amendment ACA-2026/2.

Two independent questions, evaluated separately and in this order by the orchestrator:

  1. evaluate_requested_action(referral) - does the referral's requested action fall
     within ACA-2026/1 section 3 (requires supervisor approval / must be escalated per
     section 4)? Driven by policy_rules.json, not hardcoded if/else per referral - see
     that file's header comment and DECISIONS.md > "Policy as data."

  2. evaluate_household_for_aca_2026_2(...) - does the referral concern a household
     that includes a person under 18 (ACA-2026/1 3.9, inserted by ACA-2026/2), making
     triage-note drafting itself prohibited? Only reached for referrals that passed
     check 1 (an escalated referral is never drafted regardless, so 3.9 is moot for it -
     see DECISIONS.md > "Hand-Off vs Escalation" for why this ordering is safe).

Neither function is keyed on referral_id or resident_ref - see policy_rules.json and the
age computation below, both of which operate on the referral's own content and the
household data the history service returns.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from app.models import (
    ActionDecision,
    ActionVerdict,
    HandoffDecision,
    HandoffVerdict,
    HistoryFetchOutcome,
    HistoryFetchResult,
    HouseholdMember,
    PolicyBasis,
    Referral,
)

RULES_PATH = Path(__file__).resolve().parent / "policy_rules.json"
_RULES = json.loads(RULES_PATH.read_text(encoding="utf-8"))

UNDER_18_SECTION = "ACA-2026/1 3.9"
UNDER_18_AMENDMENT_REF = "as inserted by ACA-2026/2 2.1"
UNKNOWN_HOUSEHOLD_BASIS = "ACA-2026/2 5.2"


def evaluate_requested_action(referral: Referral) -> ActionDecision:
    combined_text = f"{referral.requested_action} {referral.summary}".lower()

    for rule in _RULES["restricted_action_rules"]:
        for keyword in rule["keywords"]:
            if keyword in combined_text:
                return ActionDecision(
                    verdict=ActionVerdict.ESCALATION_REQUIRED,
                    basis=PolicyBasis(rule["section"], rule["description"]),
                )

    comm = _RULES["communication_rule"]
    action_lower = referral.requested_action.lower()
    has_comm_verb = any(v in combined_text for v in comm["verbs"])
    has_excluded_verb = any(v in action_lower for v in comm["excluded_verbs"])
    has_target = any(t in combined_text for t in comm["targets"])
    if has_comm_verb and has_target and not has_excluded_verb:
        return ActionDecision(
            verdict=ActionVerdict.ESCALATION_REQUIRED,
            basis=PolicyBasis(comm["section"], comm["description"]),
        )

    change_rule = _RULES["change_verb_noun_rule"]
    verb_pattern = "|".join(re.escape(v) for v in change_rule["verbs"])
    noun_pattern = "|".join(re.escape(n) for n in change_rule["nouns"])
    if re.search(rf"\b({verb_pattern})\b.{{0,30}}\b({noun_pattern})\b", action_lower):
        return ActionDecision(
            verdict=ActionVerdict.ESCALATION_REQUIRED,
            basis=PolicyBasis(change_rule["section"], change_rule["description"]),
        )

    if any(v in action_lower for v in _RULES["autonomous_verbs"]):
        return ActionDecision(verdict=ActionVerdict.AUTONOMOUS)

    # ACA-2026/1 6.1: where it is unclear whether an action falls within section 3,
    # it is to be treated as though it does.
    return ActionDecision(
        verdict=ActionVerdict.ESCALATION_REQUIRED,
        basis=PolicyBasis(
            _RULES["ambiguous_default_section"],
            "requested_action did not clearly match a permitted (section 2) category; "
            "treated conservatively as falling within section 3",
        ),
    )


def _age_at(dob_str: Optional[str], reference: date) -> Optional[int]:
    if not dob_str:
        return None
    try:
        year, month, day = (int(p) for p in dob_str.split("-"))
        dob = date(year, month, day)
    except (ValueError, TypeError):
        return None
    age = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        age -= 1
    return age


def evaluate_household_for_aca_2026_2(
    fetch_result: HistoryFetchResult, reference_date: date,
) -> HandoffDecision:
    if fetch_result.outcome != HistoryFetchOutcome.OK or fetch_result.record is None:
        return HandoffDecision(
            verdict=HandoffVerdict.HANDOFF_REQUIRED,
            basis=PolicyBasis(
                f"{UNDER_18_SECTION} ({UNKNOWN_HOUSEHOLD_BASIS})",
                "household composition could not be established "
                f"({fetch_result.error or fetch_result.outcome.value}); treated as "
                "though 3.9 applies",
            ),
            household_established=False,
        )

    household: list[HouseholdMember] = fetch_result.record.household
    ages: list[Optional[int]] = [_age_at(m.date_of_birth, reference_date) for m in household]

    if any(a is None for a in ages):
        unresolvable = [m.name for m, a in zip(household, ages) if a is None]
        return HandoffDecision(
            verdict=HandoffVerdict.HANDOFF_REQUIRED,
            basis=PolicyBasis(
                f"{UNDER_18_SECTION} ({UNKNOWN_HOUSEHOLD_BASIS})",
                "date of birth could not be established for household member(s) "
                f"{unresolvable}; treated as though 3.9 applies",
            ),
            household_established=False,
        )

    under_18 = [m.name for m, a in zip(household, ages) if a is not None and a < 18]
    if under_18:
        return HandoffDecision(
            verdict=HandoffVerdict.HANDOFF_REQUIRED,
            basis=PolicyBasis(
                f"{UNDER_18_SECTION} ({UNDER_18_AMENDMENT_REF})",
                f"household includes person(s) under 18: {under_18}",
            ),
            household_established=True,
        )

    return HandoffDecision(verdict=HandoffVerdict.NOT_APPLICABLE, household_established=True)
