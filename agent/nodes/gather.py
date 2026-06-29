"""gather_constraints + clarify nodes.

Every user message is analyzed by Groq first (``understand_turn``).
Rule-based parsers run only when the LLM is offline.
"""

from __future__ import annotations

from typing import Any

from agent.intake import apply_elective_inference, fill_intake_offline, is_complete
from agent.llm import llm_available
from agent.revision import revision_delta
from agent.semantic import to_config
from agent.state import PlannerState, last_user_message
from agent.understand import apply_understanding, understand_turn


def gather_constraints(state: PlannerState) -> dict[str, Any]:
    text = last_user_message(state)
    prev = state.get("config")
    base_intake = state.get("intake", {}) or {}
    # True when the previous turn asked an onboarding question and no plan
    # exists yet: this turn is an *answer* (e.g. "ENGL 119"), not a lookup.
    answering_onboarding = bool(state.get("needs_clarification")) and not state.get("plan")

    understanding, used_understand = understand_turn(text, state)
    understanding_dict = understanding.to_state_dict() if understanding else None
    llm_expected = llm_available()

    if understanding:
        intake = apply_understanding(base_intake, understanding, text=text)
        intake = fill_intake_offline(intake, text)
        llm_offline = False
    else:
        intake = fill_intake_offline(base_intake, text)
        llm_offline = llm_expected

    config, used_config = to_config(
        text,
        intake.get("reqs_key", ""),
        prev,
        understanding=understanding,
    )
    if not understanding:
        intake = fill_intake_offline(intake, text, wants_easy=int(config.get("min_easy_courses", 0)) > 0)
    # Always attempt elective capture: it only acts on explicit codes / skip,
    # a named specialization, or (offline) a career-keyword guess — so a typed
    # answer to the elective question lands even when the LLM labels the turn
    # "general". A bare greeting with no signal leaves picks untouched.
    intake = apply_elective_inference(intake, text, config, understanding=understanding)

    if not intake.get("career_goal") and all(
        intake.get(k) for k in ("program", "residency", "sequence", "start_term")
    ):
        intake["career_goal"] = "exploring options"

    complete = is_complete(intake, config)
    career_goal = intake.get("career_goal") or state.get("career_goal", "") or text
    turn_revision = revision_delta(prev, config)

    return {
        "intake": intake,
        "career_goal": career_goal,
        "config": config,
        "understanding": understanding_dict,
        "turn_revision": turn_revision,
        "needs_clarification": not complete,
        "answering_onboarding": answering_onboarding,
        "used_llm": used_understand or used_config,
        "llm_understood": used_understand,
        "llm_configured": llm_expected,
        "llm_parse_failed": llm_expected and not used_understand,
        "llm_offline": llm_offline if not used_understand else False,
    }


def clarify(state: PlannerState) -> dict[str, Any]:
    return {"needs_clarification": True}
