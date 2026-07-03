"""Conversational plan advice — grounded recommendations, no hallucination.

The advisor speaks only about courses that actually exist (real titles from the
catalog) and never claims the student uploaded or wrote the plan themselves.
When no career goal was given, it says so instead of assuming one.
"""

from __future__ import annotations

from typing import Any

from agent.llm import complete_text, llm_available
from agent.state import PlannerState, last_user_message
from data.uw_api import fetch_courses

_SYSTEM = """You are Schedugoose, a University of Waterloo course-planning advisor.

Schedugoose GENERATED the term-by-term plan shown in the UI from the student's
answers. The student did NOT upload, write, or design it — never imply they did,
and never say they "have a plan in place" as if it were pre-existing or theirs.
The plan is a PROPOSED future schedule: its courses are planned, NOT yet taken.
Never say the student "has taken", "already took", or "completed" a planned
course unless it is explicitly listed as completed.

Grounding rules (STRICT — violations are bugs):
- Use ONLY the course codes and titles listed under "Courses in the plan" and
  "Courses they could add". NEVER invent a course code, title, or description,
  and never restate what a course covers unless its title makes it obvious.
- Never recommend a course that is already in the plan as if it were missing.
- Only suggest courses from the "Courses they could add" list. If that list is
  empty, do not suggest specific courses.
- Do NOT recommend core / required courses (they're already required — the
  student takes them regardless). Only recommend electives / upper-year options
  they'd actually choose.
- When you recommend a course, ALWAYS include its prerequisites exactly as given
  in the list (e.g. "CS 486 — Intro to AI (prereq: CS 245, STAT 231)").
- If the career goal is "none stated", do NOT assume one (not data science, not
  anything). Say no specific goal was given and invite them to name one.

Style: answer their actual question conversationally; don't repeat the whole
schedule. 3-6 sentences. Reply in the user's language (English or Chinese)."""


def compact_plan_summary(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    for term in plan.get("terms", []):
        if term.get("kind") == "work":
            continue
        courses = term.get("courses") or []
        if courses:
            lines.append(f"{term.get('label')}: {', '.join(courses)}")
    return "\n".join(lines[:16])


# Core / required categories — students take these regardless, so never
# "recommend" them; recommendations should be electives / upper-year options.
_CORE_CATS = {"CS-Core", "Math-Core", "STAT-Core", "Comm", "PD"}


def _catalog() -> dict[str, Any]:
    return {c.course_id: c for c in fetch_courses()}


def _has_career(intake: dict[str, Any], state: PlannerState) -> str | None:
    goal = (intake.get("career_goal") or state.get("career_goal") or "").strip()
    if not goal or goal.lower() in ("exploring options", "exploring", "unknown", "none"):
        return None
    return goal


def _plan_ids(plan: dict[str, Any]) -> list[str]:
    return [c for t in plan.get("terms", []) for c in (t.get("courses") or [])]


def _completed_set(state: PlannerState) -> set[str]:
    intake = state.get("intake") or {}
    profile = state.get("profile") or {}
    return set(profile.get("completed") or []) | set(intake.get("completed") or [])


def _addable_courses(state: PlannerState, plan: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    """Career-KB courses THIS student could actually add.

    A recommendation is a promise of eligibility, so it passes the same gates
    as the scheduler: program restriction ("CS students only" is invisible to a
    Math student), antirequisites already on the transcript, and prerequisites
    satisfied by taken-or-planned courses (a failed prereq doesn't count —
    failed attempts never enter the completed set).
    """

    from data.restrictions import student_eligible

    intake = state.get("intake") or {}
    completed = _completed_set(state)
    in_plan = set(_plan_ids(plan))
    known = completed | in_plan
    out: list[str] = []
    for hit in state.get("rag_hits") or []:
        for cid in hit.get("courses") or []:
            c = catalog.get(cid)
            if not c or cid in known or cid in out:
                continue
            if _CORE_CATS & set(c.categories):  # skip required/core courses
                continue
            if not student_eligible(c.restricted_to, intake.get("program"), intake.get("faculty")):
                continue
            if any(a in completed for a in c.antireqs):
                continue
            from data.prefilter import prereqs_met

            if not prereqs_met(c, known):
                continue
            out.append(cid)
    return out[:6]


def _with_prereqs(ids: list[str], catalog: dict[str, Any]) -> str:
    """Format 'CS 486 — Intro to AI (prereq: CS 245, STAT 231)' for each course."""

    parts: list[str] = []
    for cid in ids:
        c = catalog.get(cid)
        if not c:
            continue
        pre = f"prereq: {', '.join(c.prereqs)}" if c.prereqs else "no prereqs"
        parts.append(f"{cid} — {c.title} ({pre})")
    return "; ".join(parts)


def _fallback_advisory(state: PlannerState) -> str:
    intake = state.get("intake") or {}
    plan = state.get("plan") or {}
    catalog = _catalog()
    career = _has_career(intake, state)
    addable = _addable_courses(state, plan, catalog)

    if career is None:
        return (
            "You haven't told me a specific career goal yet, so this is a solid general "
            "foundation for your program. Tell me a direction — for example machine learning, "
            "systems, security, or theory — and I'll tailor the electives to it."
        )
    if addable:
        return (
            f"For **{career}**, electives beyond your required courses that fit — with "
            f"prerequisites: {_with_prereqs(addable, catalog)}. Tell me a term and I'll try to slot one in."
        )
    return (
        f"For **{career}**, your plan already covers the relevant courses. "
        "Ask me to make a term lighter, swap a course, or change your sequence."
    )


def advisory_reply(state: PlannerState) -> tuple[str, bool]:
    """Natural-language advice when a plan exists. Returns (text, used_llm)."""

    if not llm_available():
        return _fallback_advisory(state), False

    intake = state.get("intake") or {}
    plan = state.get("plan") or {}
    catalog = _catalog()
    career = _has_career(intake, state)
    addable = _addable_courses(state, plan, catalog)
    in_plan = ", ".join(
        f"{cid} ({catalog[cid].title})" for cid in _plan_ids(plan) if cid in catalog
    )

    payload = (
        f"Latest user message:\n{last_user_message(state)}\n\n"
        f"Program: {intake.get('program') or 'unknown'}\n"
        f"Career goal: {career or 'none stated'}\n\n"
        f"Courses in the plan (code + real title — use these titles, invent nothing):\n{in_plan}\n\n"
        f"Courses they could add (electives beyond requirements, with prerequisites — "
        f"recommend ONLY from here, always cite the prereq):\n"
        f"{_with_prereqs(addable, catalog) or '(none)'}"
    )
    text = complete_text(_SYSTEM, payload)
    if text:
        # Post-hoc grounding check: the model may only name courses from the
        # eligibility-filtered addable list, the plan, or the transcript. A
        # small model sometimes ignores the list and pitches a course the
        # student cannot take (e.g. CS-only for a Math student) — in that case
        # discard its text and use the deterministic fallback instead.
        from agent.semantic import extract_course_codes

        allowed = set(addable) | set(_plan_ids(plan)) | _completed_set(state)
        bad = [c for c in extract_course_codes(text) if c not in allowed]
        if not bad:
            return text.strip(), True
    return _fallback_advisory(state), False
