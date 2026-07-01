"""Answer questions about a specific course code (Groq + UW catalog)."""

from __future__ import annotations

import json
import re
from typing import Any

from agent.llm import complete_text
from agent.semantic import extract_course_codes, normalize_course_code
from data.program_templates import recommended_term
from data.restrictions import student_eligible
from data.uw_api import lookup_course

_INFO_PHRASES = (
    "what is",
    "what's",
    "whats",
    "tell me about",
    "describe",
    "explain",
    "what does",
    "about the course",
    "course about",
    "know about",
    "prereq",
    "prerequisite",
    "need before",
    "before taking",
    "before i take",
    "requirement for",
    "required for",
    "vs",
    "versus",
    "compare",
    "difference between",
    "which is better",
    "which is easier",
    "when do i take",
    "when should i take",
    "what term",
)

_PLANNING_PHRASES = (
    "plan",
    "schedule",
    "lighter",
    "heavier",
    "swap",
    "change my",
    "replan",
    "avoid",
    "must take",
    "include",
    "add to",
    "drop",
)

_SYSTEM = """You are Schedugoose, a University of Waterloo course-planning assistant.
The user asked about one specific course. Answer using ONLY the course facts JSON below.
- Lead with what the course is about (use description when present).
- Mention prerequisites using prereqs_text or prereqs when present (quote UW requirements when available).
- If "restricted_to" is non-empty, the course is reserved for those students ONLY. Say so plainly and, if it doesn't match the student's program, tell them they are NOT eligible — never claim it is open to everyone.
- If "recommended_term" is present, mention that's when it's usually taken in the standard UW sequence.
- If the course appears in their plan, note which term.
- Do not invent content, instructors, or requirements.
- Be concise (2–5 sentences). Reply in the same language as the user (English or Chinese)."""


def _normalize_lookup_text(text: str) -> str:
    """Loosen casual typing: ``whatis soc101`` → ``what is soc101``."""

    low = text.lower()
    low = re.sub(r"\bwhatis\b", "what is", low)
    low = re.sub(r"\bwhats\b", "what's", low)
    low = re.sub(r"\btellmeabout\b", "tell me about", low)
    return low


def is_course_info_question(text: str) -> bool:
    """Offline fallback when Groq understanding is unavailable."""

    codes = extract_course_codes(text)
    if not codes:
        return False
    low = _normalize_lookup_text(text)
    if any(p in low for p in _PLANNING_PHRASES):
        return False
    if any(p in low for p in _INFO_PHRASES):
        return True
    # Short bare lookup: "soc101", "SOC 101?", "whatis soc101" (after normalize)
    compact = re.sub(r"[\s?.,!]", "", low)
    code_compact = codes[0].replace(" ", "").lower()
    if compact == code_compact or compact.endswith(code_compact) and len(compact) <= len(code_compact) + 8:
        return True
    return len(text.strip()) <= 28


def _plan_term_for_course(plan: dict[str, Any] | None, course_id: str) -> str | None:
    if not plan:
        return None
    for term in plan.get("terms", []):
        if course_id in (term.get("courses") or []):
            label = term.get("label") or ""
            display = term.get("display") or ""
            return f"{label} ({display})" if display else label or None
    return None


def gather_course_facts(
    course_id: str,
    *,
    intake: dict[str, Any] | None = None,
    catalog: list[Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge UW API lookup, catalog row, and plan placement."""

    course_id = normalize_course_code(course_id)
    facts = lookup_course(course_id, start_term=(intake or {}).get("start_term"))

    if catalog:
        def _field(obj: Any, key: str) -> Any:
            """Read a field from a dataclass Course or a plain dict."""
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        for course in catalog:
            cid = _field(course, "course_id")
            if cid == course_id:
                facts.setdefault("title", _field(course, "title"))
                facts.setdefault("units", _field(course, "units"))
                facts["prereqs"] = list(
                    _field(course, "prereqs") or facts.get("prereqs") or []
                )
                facts["categories"] = list(
                    _field(course, "categories") or facts.get("categories") or []
                )
                facts["restricted_to"] = list(
                    _field(course, "restricted_to") or facts.get("restricted_to") or []
                )
                break

    facts["plan_term"] = _plan_term_for_course(plan, course_id)
    if facts.get("requirements_description"):
        facts["prereqs_text"] = facts["requirements_description"]
    elif facts.get("prereqs"):
        facts["prereqs_text"] = "Prerequisites: " + ", ".join(facts["prereqs"])

    restricted = facts.get("restricted_to") or []
    if restricted:
        prog = (intake or {}).get("program")
        fac = (intake or {}).get("faculty")
        facts["eligible_for_student"] = student_eligible(restricted, prog, fac)

    rec = recommended_term(course_id)
    if rec:
        facts["recommended_term"] = rec

    # Enrich from the live UW calendar for any subject not in our catalog.
    if not facts.get("description"):
        from data.calendar import course_blurb

        blurb = course_blurb(course_id)
        if blurb:
            facts["description"] = blurb[0]
            facts["calendar_url"] = blurb[1]
            facts["found"] = True
    return facts


def _no_real_info(facts: dict[str, Any]) -> bool:
    """True when we have nothing concrete about the course (likely nonexistent)."""

    return (
        not facts.get("description")
        and not facts.get("prereqs")
        and not facts.get("categories")
        and facts.get("title") in (None, "", facts.get("course_id"))
    )


def _is_not_found(facts: dict[str, Any]) -> bool:
    return facts.get("found") is False or _no_real_info(facts)


def _not_found_message(facts: dict[str, Any]) -> str:
    cid = facts.get("course_id", "that course")
    return (
        f"I couldn't find **{cid}** in the UW catalog — double-check the course code "
        "(e.g. CS 246, STAT 231), and note the term must actually offer it."
    )


def _template_answer(facts: dict[str, Any]) -> str:
    if _is_not_found(facts):
        return _not_found_message(facts)
    cid = facts.get("course_id", "This course")
    title = facts.get("title", cid)
    lines = [f"**{cid} — {title}**"]
    desc = facts.get("description")
    if desc:
        lines.append(str(desc))
    else:
        lines.append("No official description is available in the catalog data I have.")
    prereqs = facts.get("prereqs") or []
    if prereqs:
        lines.append(f"Prerequisites: {', '.join(prereqs)}.")
    cats = facts.get("categories") or []
    if cats:
        lines.append(f"Categories: {', '.join(cats)}.")
    rec = facts.get("recommended_term")
    if rec:
        lines.append(f"Usually taken in **{rec}** in the standard UW sequence.")
    restricted = facts.get("restricted_to") or []
    if restricted:
        who = ", ".join(restricted)
        line = f"Enrollment restriction: **{who} students only**."
        if facts.get("eligible_for_student") is False:
            line += " Based on your program, you are **not eligible** to take this course."
        lines.append(line)
    term = facts.get("plan_term")
    if term:
        lines.append(f"In your current plan: scheduled in **{term}**.")
    src = facts.get("source", "unknown")
    lines.append(f"(Course data: {src})")
    return "\n".join(lines)


def answer_course_question(
    user_msg: str,
    facts: dict[str, Any],
) -> tuple[str, bool]:
    """Return (answer text, used_llm)."""

    # Never invent details for a course we couldn't find.
    if _is_not_found(facts):
        return _not_found_message(facts), False

    payload = json.dumps(facts, indent=2, default=str)
    llm_text = complete_text(
        _SYSTEM,
        f"User question:\n{user_msg}\n\nCourse facts:\n{payload}",
    )
    if llm_text:
        return llm_text.strip(), True
    return _template_answer(facts), False
