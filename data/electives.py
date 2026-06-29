"""Easy / bird-course elective pool + intent-based auto-selection."""

from __future__ import annotations

import re
from typing import Any

from data.degree_plans import parse_degree_plan, plan_from_intake
from data.uw_api import fetch_courses

EASY_THRESHOLD = 0.75

_COURSE_RE = re.compile(r"\b([A-Za-z]{2,5})\s?([0-9]{3}[A-Za-z]?)\b")

# Courses that support each specialization / minor (mock + live catalog).
_SPEC_ELECTIVES: dict[str, list[str]] = {
    "CS-Business-Specialization": ["ECON 101", "ENGL 119", "SPCOM 223", "ENGL 210"],
    "CS-AI-Specialization": ["STAT 341", "CS 486", "CS 480"],
    "CS-Computational-Math-Specialization": ["MATH 239", "CO 487", "STAT 332"],
    "CS-HCI-Specialization": ["PSYCH 101", "ARTS 130", "CS 492"],
}

_MINOR_ELECTIVES: dict[str, list[str]] = {
    "Stats-Minor": ["STAT 230", "STAT 231", "STAT 332"],
    "Math-Minor": ["MATH 239", "MATH 235", "MATH 138"],
    "Economics-Minor": ["ECON 101", "ENGL 119"],
    "Psych-Minor": ["PSYCH 101", "SOC 101"],
}

_CAREER_KEYWORDS: list[tuple[str, list[str]]] = [
    (r"\bdata sci", ["STAT 341", "CS 480", "ECON 101"]),
    (r"\bmachine learning\b|\bml\b", ["CS 480", "STAT 341", "CS 486"]),
    (r"\bbackend\b|\bsystems\b", ["CS 454", "CS 350", "CS 451"]),
    (r"\bsecurity\b|\bcrypto\b", ["CO 487", "CS 459"]),
    (r"\bbusiness\b|\bfinance\b|\bentrepreneur", ["ECON 101", "ENGL 119", "SPCOM 223"]),
    (r"\bpsych", ["PSYCH 101", "SOC 101"]),
]


def _catalog_ids() -> set[str]:
    return {c.course_id for c in fetch_courses()}


def _filter_known(codes: list[str]) -> list[str]:
    known = _catalog_ids()
    return [c for c in codes if c in known]


def _dedupe(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def easy_elective_options(completed: set[str] | None = None) -> list[dict[str, str]]:
    """Return eligible easy electives the user can choose from."""

    completed = completed or set()
    out: list[dict[str, str]] = []
    for c in fetch_courses():
        if c.course_id in completed:
            continue
        if "Elective" not in c.categories:
            continue
        if c.easiness < EASY_THRESHOLD:
            continue
        if c.course_id.upper().startswith("PD"):
            continue
        out.append({
            "course_id": c.course_id,
            "title": c.title,
            "easiness": str(round(c.easiness, 2)),
        })
    out.sort(key=lambda row: (-float(row["easiness"]), row["course_id"]))
    return out


def format_elective_menu(options: list[dict[str, str]], limit: int = 8) -> str:
    """Human-readable bullet list (optional hint only — not a required picker)."""

    lines = []
    for row in options[:limit]:
        lines.append(f"  - {row['course_id']}: {row['title']}")
    return "\n".join(lines)


def filter_known_electives(codes: list[str]) -> list[str]:
    return _dedupe(_filter_known(codes))[:5]


def infer_confident_picks(intake: dict[str, Any], text: str) -> list[str]:
    """Electives implied by an explicit specialization, minor, or course code.

    These are *strong* signals from the user — safe to act on without asking.
    Career goals and a bare "I want easy courses" are deliberately excluded:
    those are handled as a fallback (or an onboarding question) instead.
    """

    low = text.lower()
    picks: list[str] = []

    plan = plan_from_intake(intake)
    if intake.get("reqs_key"):
        fresh = parse_degree_plan(text, intake["reqs_key"])
        if fresh:
            plan = fresh

    for spec in plan.specializations:
        picks.extend(_SPEC_ELECTIVES.get(spec, []))
    for minor in plan.minors:
        picks.extend(_MINOR_ELECTIVES.get(minor, []))

    if "business" in low and re.search(r"spec\w*|special", low):
        picks.extend(_SPEC_ELECTIVES["CS-Business-Specialization"])
    if re.search(r"\bai\s+spec|\bartificial intelligence", low):
        picks.extend(_SPEC_ELECTIVES["CS-AI-Specialization"])

    for s, n in _COURSE_RE.findall(text):
        picks.append(f"{s.upper()} {n.upper()}")

    return _dedupe(_filter_known(picks))[:5]


def infer_elective_picks_fallback(
    intake: dict[str, Any],
    text: str,
    config: dict[str, Any] | None = None,
) -> list[str] | None:
    """Guess electives from degree plan, career, and message — no manual menu."""

    picks: list[str] = list(infer_confident_picks(intake, text))

    career = (intake.get("career_goal") or "").lower()
    combined = f"{text.lower()} {career}"
    for pattern, codes in _CAREER_KEYWORDS:
        if re.search(pattern, combined):
            picks.extend(codes)

    picks = _dedupe(_filter_known(picks))
    if picks:
        return picks[:5]

    cfg = config or {}
    min_easy = int(cfg.get("min_easy_courses", 0))
    if min_easy > 0:
        easy = easy_elective_options()
        return [row["course_id"] for row in easy[: max(1, min_easy)]]

    return None
