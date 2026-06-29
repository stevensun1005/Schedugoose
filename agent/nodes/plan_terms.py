"""plan_terms node: run the multi-term sequence planner.

Replaces single-term solving in the conversational flow once onboarding is
complete. The OR core still solves each individual term.
"""

from __future__ import annotations

from typing import Any

from agent.planner import plan_sequence
from agent.state import PlannerState


def plan_terms(state: PlannerState) -> dict[str, Any]:
    intake = state.get("intake", {}) or {}
    profile = state.get("profile", {}) or {}
    completed = set(profile.get("completed", []) or [])
    plan = plan_sequence(
        intake=intake,
        config=state.get("config"),
        completed=completed,
        career_goal=state.get("career_goal", ""),
    )
    return {"plan": plan, "schedule": None}
