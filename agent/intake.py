"""Onboarding intake: program -> sequence -> start term -> career -> elective picks."""

from __future__ import annotations

from typing import Any, TypedDict

from agent.semantic import extract_course_codes, has_career_hint
from data.electives import easy_elective_options, format_elective_menu
from data.sequences import (
    format_term,
    identify_program,
    match_sequence,
    parse_start_term,
    sequences_for_faculty,
)


class Intake(TypedDict, total=False):
    program: str
    faculty: str
    reqs_key: str
    sequence: str
    start_term: dict
    career_goal: str
    elective_picks: list[str]   # user-chosen bird courses; [] = skipped


def _parse_elective_picks(text: str) -> list[str] | None:
    """Return chosen course codes, or [] if user skips."""

    low = text.lower().strip()
    if any(k in low for k in ("skip", "no elective", "none", "don't care", "you pick", "surprise me")):
        return []
    codes = extract_course_codes(text)
    return codes if codes else None


def update_intake(intake: Intake, text: str, *, wants_easy: bool = False) -> Intake:
    out: Intake = dict(intake)  # type: ignore[assignment]

    if not out.get("program"):
        prog = identify_program(text)
        if prog:
            out["program"] = prog.name
            out["faculty"] = prog.faculty
            out["reqs_key"] = prog.reqs_key

    if out.get("faculty") and not out.get("sequence"):
        key = match_sequence(text, out["faculty"])
        if key:
            out["sequence"] = key

    if not out.get("start_term"):
        term = parse_start_term(text)
        if term:
            out["start_term"] = term

    if not out.get("career_goal") and has_career_hint(text):
        out["career_goal"] = text

    # Elective picker (after career is known).
    if wants_easy and out.get("elective_picks") is None:
        picks = _parse_elective_picks(text)
        if picks is not None:
            out["elective_picks"] = picks

    return out


def needs_elective_pick(intake: Intake, config: dict[str, Any] | None) -> bool:
    cfg = config or {}
    if int(cfg.get("min_easy_courses", 0)) <= 0:
        return False
    return intake.get("elective_picks") is None


def is_complete(intake: Intake, config: dict[str, Any] | None = None) -> bool:
    base = all(intake.get(k) for k in ("program", "sequence", "start_term", "career_goal"))
    if not base:
        return False
    return not needs_elective_pick(intake, config)


def next_question(intake: Intake, config: dict[str, Any] | None = None) -> str:
    if not intake.get("program"):
        return (
            "What program are you in? (e.g. Computer Science, Software Engineering, "
            "Mechatronics, Statistics) -- this sets your faculty and graduation rules."
        )
    if not intake.get("sequence"):
        faculty = intake.get("faculty", "")
        opts = sequences_for_faculty(faculty)
        listed = "; ".join(s.name for s in opts) or "regular or co-op"
        return (
            f"You're in {intake.get('program')} ({faculty}). Which co-op sequence are you on? "
            f"Options: {listed}."
        )
    if not intake.get("start_term"):
        return (
            'Which term do you start (your 1A)? e.g. "Fall 2026". '
            "I'll plan every study term forward along your sequence."
        )
    if not intake.get("career_goal"):
        return (
            "What career are you aiming for? (e.g. data science, backend, security). "
            'You can also say "keep it light" or "no mornings".'
        )
    if needs_elective_pick(intake, config):
        opts = easy_elective_options()
        menu = format_elective_menu(opts)
        return (
            "You asked for lighter / easy courses. Pick the electives you'd like "
            f"(I'll slot them when prereqs allow):\n{menu}\n"
            "Reply with course codes (e.g. ENGL 119, PSYCH 101) or say skip."
        )
    return ""
