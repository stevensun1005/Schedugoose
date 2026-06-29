"""gather_constraints + clarify nodes.

Runs onboarding intake (program -> sequence -> start term -> career), parses
preferences into a solver config, and flags when more info is needed. Intake is
persisted across turns so revision turns don't reset progress.
"""

from __future__ import annotations

from typing import Any

from agent.intake import is_complete, next_question, update_intake
from agent.semantic import to_config
from agent.state import PlannerState, last_user_message


def gather_constraints(state: PlannerState) -> dict[str, Any]:
    text = last_user_message(state)
    intake = update_intake(state.get("intake", {}) or {}, text)
    prev = state.get("config")

    # Preferences (load / weights / time / easy-course). Program-req defaults
    # come from the intake's degree template downstream.
    config, used_llm = to_config(text, intake.get("reqs_key", ""), prev)

    complete = is_complete(intake)
    career_goal = intake.get("career_goal") or state.get("career_goal", "") or text

    return {
        "intake": intake,
        "career_goal": career_goal,
        "config": config,
        "needs_clarification": not complete,
        "used_llm": used_llm,
    }


def clarify(state: PlannerState) -> dict[str, Any]:
    intake = state.get("intake", {}) or {}
    return {"clarification": next_question(intake), "needs_clarification": True}
