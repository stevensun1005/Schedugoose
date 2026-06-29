"""Program / graduation requirements (curated from the undergraduate calendar).

Requirements are expressed as ``category -> minimum number of courses``, which
maps directly onto hard constraint H4 in the solver. Categories line up with
the ``categories`` tags attached to courses in the data layer.
"""

from __future__ import annotations

# Curated requirement templates. Public calendar data, hand-maintained.
#
# Two flavours:
#   * Term-level specializations (small): used by the single-term planner / eval.
#   * Full-degree majors (cumulative): used by the multi-term sequence planner;
#     these are satisfied across all study terms, not within any single term.
PROGRAMS: dict[str, dict[str, int]] = {
    # --- term-level / specialization templates ---
    "CS-AI-Specialization": {
        "CS-AI": 2,      # at least two AI courses
        "STAT-ML": 1,    # at least one ML-flavoured stats course
        "CS-4xx": 2,     # depth: two senior CS courses
    },
    "CS-General": {
        "CS-4xx": 2,
        "CS-3xx": 1,
    },
    "Stats-DataScience": {
        "STAT-ML": 1,
        "STAT-Core": 1,
        "CS-AI": 1,
    },
    # --- full-degree (cumulative) templates ---
    # Category mins are *in addition* to hitting MIN_DEGREE_UNITS (20.0) overall.
    "CS-Major": {
        "CS-Core": 8,
        "Math-Core": 6,
        "Comm": 1,
        "STAT-Core": 2,
        "CS-3xx": 3,
        "CS-4xx": 4,
        "Elective": 8,
    },
    "DataScience-Major": {
        "CS-Core": 5,
        "Math-Core": 3,
        "STAT-Core": 2,
        "STAT-ML": 1,
        "CS-AI": 1,
        "Comm": 1,
    },
    "Eng-Generic": {
        "CS-Core": 3,
        "Math-Core": 4,
        "Comm": 1,
        "CS-3xx": 1,
    },
    "Science-Generic": {
        "CS-Core": 3,
        "Math-Core": 3,
        "Comm": 1,
        "STAT-Core": 1,
    },
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
