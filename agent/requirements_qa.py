"""Answer degree / specialization requirement questions (not just re-plan)."""

from __future__ import annotations

from typing import Any

from data.degree_plans import (
    SPECIALIZATIONS,
    plan_from_intake,
    resolve_requirements,
)
from data.uw_api import data_source

# Curated specialization blurbs (simplified from UW calendar; not a registrar source).
_SPECIALIZATION_GUIDE: dict[str, dict[str, Any]] = {
    "CS-Business-Specialization": {
        "title": "Computer Science — Business Specialization",
        "summary": (
            "On top of the Honours CS major, the Business specialization adds "
            "business-oriented coursework (communications + business electives)."
        ),
        "extra_categories": {"Comm": 1, "Elective": 2},
        "suggested_courses": [
            "ECON 101 — Microeconomics",
            "ENGL 119 / ENGL 210 — Communication",
            "SPCOM 223 — Public speaking",
            "AFM 101 / AFM 131 — Accounting & finance foundations (if offered)",
        ],
        "notes": (
            "Exact AFM/BUS course codes vary by term — Schedugoose pulls live "
            "titles from the UW Open Data API when your key is configured."
        ),
    },
    "CS-AI-Specialization": {
        "title": "Computer Science — AI Specialization",
        "summary": "Adds AI/ML depth on top of the CS major.",
        "extra_categories": SPECIALIZATIONS["CS-AI-Specialization"],
        "suggested_courses": ["CS 486", "CS 480", "STAT 341"],
        "notes": "",
    },
}


def is_requirements_question(text: str) -> bool:
    from agent.semantic import extract_course_codes

    if extract_course_codes(text):
        return False
    low = text.lower()
    asks = any(p in low for p in (
        "what courses", "which courses", "what classes", "what do i need",
        "courses do i need", "courses i need", "need to take", "requirements",
        "how do i get", "how to get", "what is required",
    ))
    topic = any(p in low for p in (
        "specialization", "specialisation", "spec", "minor", "major", "degree", "graduate",
        "business", "ai ", "artificial intelligence",
    ))
    return asks and topic


def _pick_specialization_key(intake: dict, text: str) -> str | None:
    low = text.lower()
    if "business" in low:
        return "CS-Business-Specialization"
    if "ai" in low or "artificial intelligence" in low:
        return "CS-AI-Specialization"
    plan = plan_from_intake(intake)
    return plan.specializations[0] if plan.specializations else None


def format_requirements_answer(
    text: str,
    intake: dict[str, Any],
    plan: dict[str, Any] | None,
) -> str:
    spec_key = _pick_specialization_key(intake, text)
    if not spec_key:
        return (
            "Which specialization are you asking about? "
            "(e.g. Business, AI, Computational Math)"
        )

    guide = _SPECIALIZATION_GUIDE.get(spec_key, {})
    plan_obj = plan_from_intake(intake)
    if spec_key not in plan_obj.specializations and "business" in text.lower():
        plan_obj = type(plan_obj)(
            kind="major_specialization",
            primary=plan_obj.primary,
            specializations=(spec_key,),
            minors=plan_obj.minors,
            extra_majors=plan_obj.extra_majors,
        )
    merged = resolve_requirements(plan_obj)
    spec_extra = SPECIALIZATIONS.get(spec_key, {})

    lines = [
        f"**{guide.get('title', spec_key)}**",
        guide.get("summary", ""),
        "",
        "Extra category requirements (on top of CS major):",
    ]
    for cat, n in spec_extra.items():
        lines.append(f"  - {cat}: at least {n} course(s)")

    lines.append("")
    lines.append("Suggested courses toward this specialization:")
    for item in guide.get("suggested_courses", []):
        lines.append(f"  - {item}")

    if plan:
        in_plan = _courses_for_spec(plan, spec_key)
        if in_plan:
            lines.append("")
            lines.append(f"Already in your current plan: {', '.join(in_plan)}")
        rem = plan.get("remaining_requirements") or {}
        if rem:
            lines.append(f"Still to schedule later: {', '.join(f'{k} (+{v})' for k, v in rem.items())}")

    src = data_source()
    lines.append("")
    lines.append(
        f"Course data: **{src}** (UW Open Data API when `live`). "
        "Below is your updated term-by-term schedule."
        if src.startswith("live")
        else "Course data: **mock catalog** — check UW_API_KEY and restart if you expected live data."
    )
    note = guide.get("notes")
    if note:
        lines.append(note)
    return "\n".join(lines)


def _courses_for_spec(plan: dict[str, Any], spec_key: str) -> list[str]:
    """Courses in the plan that help toward a specialization."""

    business = {"ECON 101", "ENGL 119", "ENGL 210", "SPCOM 223", "AFM 101", "AFM 131"}
    ai = {"CS 486", "CS 480", "STAT 341", "CS 484"}
    pool = business if "Business" in spec_key else ai
    found: list[str] = []
    for t in plan.get("terms", []):
        for c in t.get("courses", []):
            if c in pool and c not in found:
                found.append(c)
    return found
