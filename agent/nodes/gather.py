"""gather_constraints + clarify nodes.

Every user message is analyzed by Groq first (``understand_turn``).
Rule-based parsers run only when the LLM is offline.
"""

from __future__ import annotations

from typing import Any

from agent.intake import (
    apply_elective_inference,
    fill_intake_offline,
    is_complete,
    parse_entering_term,
    parse_standing,
)
from agent.llm import llm_available
from agent.revision import revision_delta
from agent.semantic import extract_course_codes, to_config
from agent.state import PlannerState, last_user_message
from agent.understand import apply_understanding, understand_turn


# Config keys whose change this turn means the plan must be re-solved.
_PLAN_CONFIG_KEYS = (
    "credit_load", "weights", "min_easy_courses", "time_prefs",
    "term_avoid", "term_requirements", "must_avoid", "must_include",
)

# Imperative cues that mean "change my plan" (vs a question that merely mentions
# workload words like "how heavy is 2A?"). Guards config drift from re-planning.
_COMMAND_STARTS = (
    "make", "change", "swap", "replace", "add", "remove", "drop", "avoid",
    "set", "move", "keep", "pin", "include", "exclude", "put", "no ", "not ",
    "without", "only", "just", "give me", "i want", "i'd like", "can you make",
)
_COMMAND_CONTAINS = (
    "make it", "make my", "lighter", "heavier", "instead", "no music", "no morning",
    "no friday", "avoid", "without", "swap", "replace", "only ", "fewer",
    "3 course", "three course", "2 course", "two course", "4 course", "four course",
    "5 course", "five course", "earlier start", "later start", "change my",
)


def _is_command(text: str) -> bool:
    low = text.lower().strip()
    if any(low.startswith(s) for s in _COMMAND_STARTS):
        return True
    return any(c in low for c in _COMMAND_CONTAINS)


def _plan_config_changed(prev: dict[str, Any] | None, config: dict[str, Any], text: str) -> bool:
    prev = prev or {}
    if not prev:
        return False  # first config — the "no plan yet" path handles the first solve
    changed = any(prev.get(k) != config.get(k) for k in _PLAN_CONFIG_KEYS)
    return changed and _is_command(text)


def _filter_ineligible_config_courses(
    config: dict[str, Any], intake: dict[str, Any], state: PlannerState,
) -> None:
    """Drop must_include / term-pin courses the student is not eligible for."""

    from data.restrictions import student_eligible
    from data.uw_api import fetch_courses

    program, faculty = intake.get("program"), intake.get("faculty")
    completed = set((state.get("profile") or {}).get("completed") or [])
    completed |= set(intake.get("completed") or [])
    if not (program or completed):
        return

    try:
        catalog = {c.course_id: c for c in fetch_courses()}
    except Exception:
        return

    def _ok(cid: str) -> bool:
        c = catalog.get(cid)
        if c is None:
            return True  # unknown course — leave it; prefilter decides later
        if not student_eligible(c.restricted_to, program, faculty):
            return False
        if any(a in completed for a in c.antireqs):
            return False
        return True

    if config.get("must_include"):
        config["must_include"] = [c for c in config["must_include"] if _ok(c)]
    for key in ("term_requirements",):
        by_term = config.get(key) or {}
        for slot, codes in list(by_term.items()):
            by_term[slot] = [c for c in codes if not c[0].isalpha() or " " not in c or _ok(c)]


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

    # Eligibility gate on config course intents: an LLM-suggested must_include
    # the student can't take ("CS students only", antireq already on the
    # transcript) must never enter the solver config — downstream the planner
    # would silently drop it while replies treat config codes as trustworthy.
    _filter_ineligible_config_courses(config, intake, state)

    # Standing / transcript — captured during onboarding (before a plan exists).
    # A brand-new student is the default; we only record what they actually tell us.
    profile_update: dict[str, Any] | None = None
    if not state.get("plan"):
        standing, completed_codes = parse_standing(text)
        if standing:
            intake["standing"] = standing
        entering = parse_entering_term(text)
        if entering:
            intake["entering_term"] = entering
            if entering != "1A":  # "first year" -> 1A is a NEW student, not returning
                intake["standing"] = "returning"
        # A pasted transcript: several course codes at once, even without a
        # keyword like "completed". Treat as the returning-student transcript.
        if not completed_codes:
            bulk = extract_course_codes(text)
            if len(bulk) >= 3:
                completed_codes = bulk
        if completed_codes:
            intake["standing"] = "returning"
            prev_completed = list((state.get("profile") or {}).get("completed") or [])
            merged = list(dict.fromkeys(prev_completed + completed_codes))
            intake["completed"] = merged
            profile_update = {**(state.get("profile") or {}), "completed": merged}
            # A pasted transcript is an onboarding answer, not a "what is CS 135?" lookup.
            answering_onboarding = True

    # Profile changes after a plan exists ("change my start to Winter 2027",
    # "switch to sequence 2", "actually I'm international") — overwrite when the
    # user names a new, different value. Onboarding (no plan) never overwrites.
    if state.get("plan"):
        from data.degree_plans import parse_residency
        from data.sequences import match_sequence, parse_start_term

        new_start = parse_start_term(text)
        if new_start and new_start != intake.get("start_term"):
            intake["start_term"] = new_start
        new_seq = match_sequence(text, intake.get("faculty", ""))
        if new_seq and new_seq != intake.get("sequence"):
            intake["sequence"] = new_seq
        new_res = parse_residency(text)
        if new_res and new_res != intake.get("residency"):
            intake["residency"] = new_res

    # A specialization / minor added after the plan exists ("I also want the
    # business specialization") — pull in its electives so the re-plan reflects it.
    degree_changed = state.get("plan") and base_intake.get("degree_plan") != intake.get("degree_plan")
    if degree_changed:
        from data.electives import infer_confident_picks

        confident = infer_confident_picks(intake, text)
        if confident:
            existing = list(intake.get("elective_picks") or [])
            intake["elective_picks"] = list(dict.fromkeys(existing + confident))

    needed_for_default = ("program", "residency", "sequence", "start_term")
    if intake.get("transcript_uploaded") or intake.get("entering_term") not in (None, "", "1A", "1B"):
        # Residency is skipped mid-degree — don't let it block the no-career default
        # (otherwise career_goal falls back to the raw message text downstream).
        needed_for_default = ("program", "sequence", "start_term")
    if not intake.get("career_goal") and all(intake.get(k) for k in needed_for_default):
        intake["career_goal"] = "exploring options"

    complete = is_complete(intake, config)
    career_goal = intake.get("career_goal") or state.get("career_goal", "") or text
    turn_revision = revision_delta(prev, config)
    config_changed = _plan_config_changed(prev, config, text)
    profile_changed = bool(degree_changed) or any(
        base_intake.get(k) and base_intake.get(k) != intake.get(k)
        for k in ("program", "residency", "sequence", "start_term")
    )

    out_state: dict[str, Any] = {
        "intake": intake,
        "career_goal": career_goal,
        "config": config,
        "understanding": understanding_dict,
        "turn_revision": turn_revision,
        "needs_clarification": not complete,
        "answering_onboarding": answering_onboarding,
        "config_changed": config_changed,
        "profile_changed": profile_changed,
        "used_llm": used_understand or used_config,
        "llm_understood": used_understand,
        "llm_configured": llm_expected,
        "llm_parse_failed": llm_expected and not used_understand,
        "llm_offline": llm_offline if not used_understand else False,
    }
    if profile_update is not None:
        out_state["profile"] = profile_update
    return out_state


def clarify(state: PlannerState) -> dict[str, Any]:
    return {"needs_clarification": True}
