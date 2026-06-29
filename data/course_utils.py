"""Course metadata helpers: level, PD/co-op, degree credit."""

from __future__ import annotations

import re

from scheduler.types import Course

_LEVEL_RE = re.compile(r"-(\d)xx$")


def course_level(course: Course) -> int:
    """Numeric level from category tags (1-4). 0 = open elective, no level cap."""

    levels = []
    for cat in course.categories:
        m = _LEVEL_RE.search(cat)
        if m:
            levels.append(int(m.group(1)))
    return max(levels) if levels else 0


def term_year(slot_label: str) -> int:
    """Study-term year from slot label (1A -> 1, 4B -> 4)."""

    if slot_label and slot_label[0].isdigit():
        return int(slot_label[0])
    return 4


def is_pd(course: Course) -> bool:
    """Professional Development courses (co-op only, no degree credit)."""

    return "PD" in course.categories or course.course_id.upper().startswith("PD ")


def counts_toward_degree(course: Course) -> bool:
    return not is_pd(course) and course.units > 0


def eligible_for_study_term(course: Course, slot_label: str) -> bool:
    """A course belongs in a study term only if level and type allow it."""

    if is_pd(course):
        return False
    level = course_level(course)
    if level == 0:
        return True
    return level <= term_year(slot_label)


def academic_units(courses: list[Course]) -> float:
    return sum(c.units for c in courses if counts_toward_degree(c))
