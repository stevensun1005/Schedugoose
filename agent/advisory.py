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


def _titles() -> dict[str, str]:
    return {c.course_id: c.title for c in fetch_courses()}


def _has_career(intake: dict[str, Any], state: PlannerState) -> str | None:
    goal = (intake.get("career_goal") or state.get("career_goal") or "").strip()
    if not goal or goal.lower() in ("exploring options", "exploring", "unknown", "none"):
        return None
    return goal


def _plan_ids(plan: dict[str, Any]) -> list[str]:
    return [c for t in plan.get("terms", []) for c in (t.get("courses") or [])]


def _addable_courses(state: PlannerState, plan: dict[str, Any], titles: dict[str, str]) -> list[str]:
    """Real catalog courses suggested by the career KB that aren't already planned."""

    in_plan = set(_plan_ids(plan))
    out: list[str] = []
    for hit in state.get("rag_hits") or []:
        for cid in hit.get("courses") or []:
            if cid in titles and cid not in in_plan and cid not in out:
                out.append(cid)
    return out[:8]


def _with_titles(ids: list[str], titles: dict[str, str]) -> str:
    return ", ".join(f"{cid} ({titles[cid]})" for cid in ids if cid in titles)


def _fallback_advisory(state: PlannerState) -> str:
    intake = state.get("intake") or {}
    plan = state.get("plan") or {}
    titles = _titles()
    career = _has_career(intake, state)
    addable = _addable_courses(state, plan, titles)

    if career is None:
        return (
            "You haven't told me a specific career goal yet, so this is a solid general "
            "foundation for your program. Tell me a direction — for example machine learning, "
            "systems, security, or theory — and I'll tailor the electives to it."
        )
    if addable:
        return (
            f"For **{career}**, courses that fit and aren't in your plan yet: "
            f"{_with_titles(addable, titles)}. Tell me a term and I'll try to swap one in."
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
    titles = _titles()
    career = _has_career(intake, state)
    addable = _addable_courses(state, plan, titles)
    in_plan = _with_titles(_plan_ids(plan), titles)

    payload = (
        f"Latest user message:\n{last_user_message(state)}\n\n"
        f"Program: {intake.get('program') or 'unknown'}\n"
        f"Career goal: {career or 'none stated'}\n\n"
        f"Courses in the plan (code + real title — use these titles, invent nothing):\n{in_plan}\n\n"
        f"Courses they could add (career-KB suggestions not already planned):\n"
        f"{_with_titles(addable, titles) or '(none)'}"
    )
    text = complete_text(_SYSTEM, payload)
    if text:
        return text.strip(), True
    return _fallback_advisory(state), False
