"""Candidate pre-filtering (hard constraint H6).

Prerequisites, term availability, study-term level caps, and PD exclusion are
handled here -- not in the solver.
"""

from __future__ import annotations

from dataclasses import replace

from data.course_utils import eligible_for_study_term, is_pd
from scheduler.types import Course


def prereqs_met(course: Course, completed: set[str]) -> bool:
    """All listed prerequisites must be in the completed-course set."""

    return all(p in completed for p in course.prereqs)


def prefilter_candidates(
    courses: list[Course],
    completed: set[str] | None = None,
    term: str | None = None,
    *,
    slot_label: str | None = None,
    study_term: bool = True,
) -> list[Course]:
    """Return only courses eligible to be scheduled."""

    completed = completed or set()
    out: list[Course] = []
    for c in courses:
        if c.course_id in completed:
            continue
        if study_term:
            if is_pd(c):
                continue
            if slot_label and not eligible_for_study_term(c, slot_label):
                continue
        elif not is_pd(c):
            continue  # work terms only take PD
        if study_term and not prereqs_met(c, completed):
            continue
        sections = [
            s for s in c.sections
            if term is None or not s.term or s.term in ("ANY", term)
        ]
        sections = [s for s in sections if s.has_space]
        if not sections:
            continue
        out.append(replace(c, sections=sections))
    return out
