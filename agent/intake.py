"""Onboarding intake: program -> residency -> degree plan -> sequence -> start -> career."""

from __future__ import annotations

from typing import Any, TypedDict

from agent.semantic import extract_course_codes
from data.degree_plans import (
    parse_degree_plan,
    parse_residency,
    plan_from_intake,
    plan_to_dict,
)
from data.electives import (
    filter_known_electives,
    infer_confident_picks,
    infer_elective_picks_fallback,
)
from data.sequences import (
    identify_program,
    match_sequence,
    parse_start_term,
    sequences_for_faculty,
)


class Intake(TypedDict, total=False):
    program: str
    faculty: str
    reqs_key: str
    residency: str
    degree_plan: dict
    sequence: str
    start_term: dict
    career_goal: str
    elective_picks: list[str]


def _parse_elective_picks(text: str) -> list[str] | None:
    low = text.lower().strip()
    if any(k in low for k in ("skip", "no elective", "none", "don't care", "you pick", "surprise me")):
        return []
    codes = extract_course_codes(text)
    return codes if codes else None


def _parse_residency_answer(text: str) -> str | None:
    low = text.lower().strip()
    if parse_residency(text):
        return parse_residency(text)
    if low in ("yes", "y", "yeah", "yep", "international", "intl"):
        return "international"
    if low in ("no", "n", "nope", "domestic", "canadian"):
        return "domestic"
    return None


def fill_intake_offline(intake: Intake, text: str, *, wants_easy: bool = False) -> Intake:
    """Rule-based intake fill — only when Groq is unavailable."""

    from agent.career import parse_career_goal

    out: Intake = dict(intake)  # type: ignore[assignment]

    if not out.get("program"):
        prog = identify_program(text)
        if prog:
            out["program"] = prog.name
            out["faculty"] = prog.faculty
            out["reqs_key"] = prog.reqs_key

    if not out.get("residency"):
        res = parse_residency(text) or _parse_residency_answer(text)
        if res:
            out["residency"] = res

    if out.get("reqs_key"):
        parsed = parse_degree_plan(text, out["reqs_key"])
        if parsed:
            out["degree_plan"] = plan_to_dict(parsed)

    if out.get("faculty") and not out.get("sequence"):
        key = match_sequence(text, out["faculty"])
        if key:
            out["sequence"] = key

    if not out.get("start_term"):
        term = parse_start_term(text)
        if term:
            out["start_term"] = term

    if not out.get("career_goal"):
        cg = parse_career_goal(text, out)
        if cg:
            out["career_goal"] = cg

    if wants_easy and out.get("elective_picks") is None:
        picks = _parse_elective_picks(text)
        if picks is not None:
            out["elective_picks"] = picks

    return out


# Backward-compatible alias
update_intake = fill_intake_offline


def apply_elective_inference(
    intake: Intake,
    text: str,
    config: dict[str, Any] | None,
    *,
    understanding: Any | None = None,
) -> Intake:
    from agent.intent_schema import TurnUnderstanding

    out: Intake = dict(intake)  # type: ignore[assignment]
    if out.get("elective_picks") is not None:
        return out

    # Explicit course codes or an explicit "skip" — honor in any mode. This is
    # how a typed answer to the elective question ("ENGL 119, PSYCH 101") lands,
    # whether or not the LLM understanding layer is active.
    explicit = _parse_elective_picks(text)
    if explicit is not None:
        out["elective_picks"] = explicit
        return out

    if isinstance(understanding, TurnUnderstanding):
        if understanding.elective_skip:
            out["elective_picks"] = []
            return out
        if understanding.suggested_electives:
            picks = filter_known_electives(understanding.suggested_electives)
            if picks:
                out["elective_picks"] = picks
                return out

    # Strong signal from a named specialization / minor / code in the message.
    confident = infer_confident_picks(out, text)
    if confident:
        out["elective_picks"] = confident
        return out

    # No strong signal. If the student asked for at least one easy course,
    # defer to an onboarding question rather than guessing for them.
    if int((config or {}).get("min_easy_courses", 0)) > 0:
        return out

    # Offline only: best-effort guess from career keywords / easy pool.
    if understanding is None:
        inferred = infer_elective_picks_fallback(out, text, config)
        if inferred is not None:
            out["elective_picks"] = inferred
    return out


def needs_elective_pick(intake: Intake, config: dict[str, Any] | None) -> bool:
    """Ask the student to pick electives only when they wanted easy courses
    and we have no picks yet — otherwise electives are inferred silently."""

    return (
        int((config or {}).get("min_easy_courses", 0)) > 0
        and intake.get("elective_picks") is None
    )


def is_complete(intake: Intake, config: dict[str, Any] | None = None) -> bool:
    base = all(intake.get(k) for k in ("program", "residency", "sequence", "start_term", "career_goal"))
    return base and not needs_elective_pick(intake, config)


def next_question(intake: Intake, config: dict[str, Any] | None = None) -> str:
    if not intake.get("program"):
        return "What program are you in?"
    if not intake.get("residency"):
        return "Are you an international student? (yes/no)"
    if not intake.get("sequence"):
        return "Which co-op sequence are you on?"
    if not intake.get("start_term"):
        return "Which term do you start (your 1A)? e.g. Fall 2026"
    if not intake.get("career_goal"):
        return "What career or field are you aiming for?"
    if needs_elective_pick(intake, config):
        return (
            "You wanted at least one lighter course — name any electives you'd like "
            "(e.g. MUSIC 116, ENGL 119), or say 'skip' and I'll pick easy ones for you."
        )
    return ""


def degree_plan_display(intake: Intake) -> str:
    return plan_from_intake(intake).display()
