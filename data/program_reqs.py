"""Program / graduation requirements (curated from the undergraduate calendar).

Full degree plans (major + minor + specialization + multi-major) live in
``data.degree_plans``; this module keeps legacy single-template lookups and
shared graduation constants.
"""

from __future__ import annotations

from data.degree_plans import MAJORS, SPECIALIZATIONS, merge_requirements

# Legacy flat map for single-term planner / eval (majors + specializations).
PROGRAMS: dict[str, dict[str, int]] = {
    **MAJORS,
    **SPECIALIZATIONS,
    "CS-General": {"CS-4xx": 2, "CS-3xx": 1},
    "Stats-DataScience": {"STAT-ML": 1, "STAT-Core": 1, "CS-AI": 1},
}

DEFAULT_PROGRAM = "CS-AI-Specialization"

# UW Honours CS: 40 half-courses = 20.0 academic credits to graduate.
MIN_DEGREE_UNITS = 20.0
MIN_DEGREE_COURSES = 40


def get_program_reqs(program: str | None = None) -> dict[str, int]:
    """Return the requirement map for a program (default if unknown)."""

    if program and program in PROGRAMS:
        return dict(PROGRAMS[program])
    return dict(PROGRAMS[DEFAULT_PROGRAM])


def list_programs() -> list[str]:
    return list(PROGRAMS.keys())
