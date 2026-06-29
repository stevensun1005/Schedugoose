"""Standard first-year course templates + recommended timelines (UW calendar).

Curated from the University of Waterloo undergraduate advising pages so the
planner anchors first year to the *official* recommended courses, and the
advisor can cite them and say when milestone courses are normally taken.

Sources:
- Math/CS first year — https://uwaterloo.ca/new-math-students/course-selection
- CS suggested term sequence — https://cs.uwaterloo.ca/suggested-sequences
- CS prerequisite chain — https://cs.uwaterloo.ca/.../cs-prerequisite-chart
- Software Engineering sample schedule — https://uwaterloo.ca/software-engineering

These are representative of the published sequences, not a registrar audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProgramTemplate:
    program: str
    # Standard first-year courses by term. The Math faculty pattern is "three
    # math (incl. CS) + two non-math" per term; we pin the three core and let
    # the planner fill the two non-math (a communication/language + an elective).
    first_year: dict[str, list[str]]
    schedulable: bool   # True when these courses exist in our catalog
    source: str = ""
    note: str = ""


# Math-faculty first year (CS, Math, Data Science, Stats) is shared core.
_MATH_FIRST_YEAR = {
    "1A": ["CS 135", "MATH 135", "MATH 137"],
    "1B": ["CS 136", "MATH 136", "MATH 138"],
}

TEMPLATES: dict[str, ProgramTemplate] = {
    "Computer Science": ProgramTemplate(
        "Computer Science", _MATH_FIRST_YEAR, schedulable=True,
        source="uwaterloo.ca/new-math-students/course-selection",
        note="Five courses (2.5 units) per term: CS + two MATH, plus two non-math.",
    ),
    "Mathematics": ProgramTemplate(
        "Mathematics", _MATH_FIRST_YEAR, schedulable=True,
        source="uwaterloo.ca/new-math-students/course-selection",
    ),
    "Data Science": ProgramTemplate(
        "Data Science", _MATH_FIRST_YEAR, schedulable=True,
        source="uwaterloo.ca/new-math-students/course-selection",
    ),
    "Statistics": ProgramTemplate(
        "Statistics", _MATH_FIRST_YEAR, schedulable=True,
        source="uwaterloo.ca/new-math-students/course-selection",
    ),
    # Engineering programs use their own subjects (SE/ECE/CHE) that aren't in
    # this catalog — kept as reference so the advisor can cite them accurately.
    "Software Engineering": ProgramTemplate(
        "Software Engineering",
        {
            "1A": ["CS 137", "MATH 115", "MATH 117", "SE 101", "CHE 102"],
            "1B": ["CS 138", "MATH 119", "ECE 124", "ECE 140", "SE 102", "ECE 192"],
        },
        schedulable=False,
        source="uwaterloo.ca/software-engineering",
        note="Lockstep engineering program — courses are fixed, not chosen.",
    ),
}


# Recommended study term for milestone courses (CS suggested sequence / prereq
# chain). Used to explain timing and answer "when do I take X?".
TIMELINE: dict[str, str] = {
    "CS 135": "1A", "MATH 135": "1A", "MATH 137": "1A",
    "CS 136": "1B", "MATH 136": "1B", "MATH 138": "1B",
    "CS 245": "2A", "CS 246": "2A", "MATH 239": "2A", "STAT 230": "2A",
    "CS 240": "2B", "CS 241": "2B", "CS 251": "2B", "STAT 231": "2B",
    "CS 341": "3A", "CS 350": "3A", "STAT 332": "3A",
    "CS 360": "3B", "CS 370": "3B", "CS 348": "3B",
}


def template_for(program: str | None) -> ProgramTemplate | None:
    return TEMPLATES.get(program or "")


def first_year_pins(program: str | None, catalog_ids: set[str]) -> dict[str, list[str]]:
    """First-year course pins per term, limited to courses we can schedule."""

    tpl = template_for(program)
    if not tpl_schedulable(tpl):
        return {}
    return {
        term: [c for c in courses if c in catalog_ids]
        for term, courses in tpl.first_year.items()  # type: ignore[union-attr]
    }


def tpl_schedulable(tpl: ProgramTemplate | None) -> bool:
    return bool(tpl and tpl.schedulable)


def recommended_term(course_id: str) -> str | None:
    """The study term a course is normally taken (e.g. 'CS 246' -> '2A')."""

    return TIMELINE.get(course_id)


def format_first_year(program: str | None) -> str | None:
    """Human-readable standard first-year for a program (for advice / Q&A)."""

    tpl = template_for(program)
    if not tpl:
        return None
    lines = [f"Standard first year for **{tpl.program}** (UW {tpl.source}):"]
    for term, courses in tpl.first_year.items():
        lines.append(f"  - {term}: {', '.join(courses)}")
    if tpl.note:
        lines.append(tpl.note)
    if not tpl.schedulable:
        lines.append("(These are fixed lockstep courses outside this planner's course data.)")
    return "\n".join(lines)
