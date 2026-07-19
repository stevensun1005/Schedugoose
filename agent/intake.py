"""Onboarding intake: program -> residency -> degree plan -> sequence -> start -> career."""

from __future__ import annotations

import re as _re
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
    standing: str          # "new" | "returning"
    completed: list[str]   # transcript: course codes already taken


_NEW_STUDENT_WORDS = (
    "new student", "brand new", "first year", "first-year", "1st year", "1a",
    "just starting", "starting fresh", "incoming", "haven't taken", "havent taken",
    "no courses", "none yet", "nothing yet", "fresh", "from scratch", "just started",
)
_DONE_CONTEXT = (
    "taken", "took", "completed", "complete", "finished", "done", "passed",
    "already did", "credit for", "transferred", "so far", "this is my transcript",
    # currently-enrolled courses count as taken for planning (they'll be done
    # before any planned term starts) — same treatment as transcript in-progress
    "enrolled", "currently taking", "taking this term",
)


def parse_standing(text: str) -> tuple[str | None, list[str]]:
    """Detect whether the student is new or returning, plus any completed courses.

    Returns ``(standing, completed_codes)`` — standing is "new", "returning", or
    None when the message says nothing about it.
    """

    low = text.lower()
    codes = extract_course_codes(text)
    if codes and any(k in low for k in _DONE_CONTEXT):
        return "returning", codes
    if any(k in low for k in _NEW_STUDENT_WORDS):
        return "new", []
    return None, []


_ENTERING_RE = _re.compile(
    r"(?:going into|entering|heading into|about to start|starting|begin(?:ning)?|"
    r"i'?m in|i am in|now in|currently in|coming up on|into my)\s+(1[ab]|2[ab]|3[ab]|4[ab])\b",
    _re.I,
)
# Allow a couple of words between the slot and the noun: "2A CS student".
_STANDING_RE = _re.compile(
    r"\b(1[ab]|2[ab]|3[ab]|4[ab])\s+(?:\w+\s+){0,2}(?:student|standing|term)\b", _re.I
)
# Ordinal year → the A term of that year ("4th year" -> "4A"). We default to the
# first half; the student can say "4B" to refine.
_YEAR_ORDINAL_RE = _re.compile(
    r"\b(?:(1st|first|2nd|second|3rd|third|4th|fourth|final|senior)[\s-]*year"
    r"|year[\s-]*([1-4])|in\s+(?:my\s+)?year\s+([1-4]))\b",
    _re.I,
)
_ORDINAL_TO_SLOT = {
    "1st": "1A", "first": "1A", "1": "1A",
    "2nd": "2A", "second": "2A", "2": "2A",
    "3rd": "3A", "third": "3A", "3": "3A",
    "4th": "4A", "fourth": "4A", "final": "4A", "senior": "4A", "4": "4A",
}


def parse_entering_term(text: str) -> str | None:
    """The academic term a returning student is entering, e.g. "going into 2B" -> "2B".

    Handles explicit slots ("2B", "going into 3A") and ordinal years
    ("4th year", "final year", "year 3" -> the A term of that year). Returns an
    upper-case slot label (``"2B"``) or None when nothing is named.
    """

    m = _ENTERING_RE.search(text) or _STANDING_RE.search(text)
    if m:
        return m.group(1).upper()
    y = _YEAR_ORDINAL_RE.search(text)
    if y:
        token = (y.group(1) or y.group(2) or y.group(3) or "").lower()
        return _ORDINAL_TO_SLOT.get(token)
    return None


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
    needed = ["program", "residency", "sequence", "start_term", "career_goal"]
    # Residency only drives the 1A language pin — irrelevant mid-degree.
    if intake.get("entering_term") not in (None, "", "1A", "1B"):
        needed.remove("residency")
    # A transcript answers everything it can; don't block the plan on a career
    # question — plan the general foundation and invite a direction after.
    if intake.get("transcript_uploaded"):
        needed.remove("career_goal")
    base = all(intake.get(k) for k in needed)
    return base and not needs_elective_pick(intake, config)


def next_question(intake: Intake, config: dict[str, Any] | None = None) -> str:
    returning = intake.get("standing") == "returning" or intake.get("entering_term")
    entering = intake.get("entering_term")
    mid_degree = entering not in (None, "", "1A", "1B")
    if not intake.get("program"):
        return "What program are you in?"
    # A returning student's transcript is the highest-value thing to collect: it
    # tells us exactly what to skip. Ask for it before the generic profile items.
    if returning and not intake.get("completed"):
        yr = f"your {entering} term" if entering else "your current year"
        return (
            f"Since you're already into {yr}, paste the courses you've completed "
            "(or your transcript text) so I skip them — e.g. \"CS 135, CS 136, "
            "MATH 135, MATH 137, ...\". You can also say 'skip' to plan the standard sequence."
        )
    if not intake.get("residency") and not mid_degree:
        return "Are you an international student? (yes/no)"
    if not intake.get("sequence"):
        fac = intake.get("faculty")
        if fac == "Math":
            return (
                "Which sequence — Regular (no co-op), or co-op Sequence 1, 2, 3, or 4? "
                "(Sequence 1 is the most common; they differ in when your work terms fall.)"
            )
        if fac == "Engineering":
            return (
                "Which co-op stream — Stream 4 (earlier first work term) or "
                "Stream 8 (more time to settle in before your first co-op)?"
            )
        return "Are you in a co-op or regular (non-co-op) sequence?"
    if not intake.get("start_term"):
        if entering and entering != "1A":
            return f"When does your next term ({entering}) start? e.g. Fall 2026"
        return "Which term do you start (your 1A)? e.g. Fall 2026"
    if not intake.get("career_goal") and not intake.get("transcript_uploaded"):
        return "What career or field are you aiming for?"
    if needs_elective_pick(intake, config):
        return (
            "You wanted at least one lighter course — name any electives you'd like "
            "(e.g. MUSIC 116, ENGL 119), or say 'skip' and I'll pick easy ones for you."
        )
    return ""


def degree_plan_display(intake: Intake) -> str:
    return plan_from_intake(intake).display()
