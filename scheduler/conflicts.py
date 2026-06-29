"""Time-conflict preprocessing.

Precompute every overlapping section pair so the solver only adds a small,
exact set of ``x[s] + x[s'] <= 1`` constraints (hard constraint H2).
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

from scheduler.types import Course, Section, iter_sections


def find_conflicts(courses: Iterable[Course]) -> list[tuple[str, str]]:
    """Return the list of conflicting section-id pairs across all courses.

    Two sections of the *same* course+component are not flagged here; the
    course-section linking constraint (H1) already forces at most one of them.
    Cross-component overlaps within a course *are* real conflicts (you can't be
    in a LEC and its LAB at the same time) and are included.
    """

    sections: list[Section] = list(iter_sections(courses))
    conflicts: list[tuple[str, str]] = []
    for a, b in combinations(sections, 2):
        if a.course_id == b.course_id and a.component == b.component:
            continue
        if a.conflicts_with(b):
            conflicts.append((a.id, b.id))
    return conflicts


def conflict_graph(courses: Iterable[Course]) -> dict[str, set[str]]:
    """Adjacency view of the conflict relation, handy for diagnostics."""

    graph: dict[str, set[str]] = {}
    for a, b in find_conflicts(courses):
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph
