"""Schedugoose OR core.

The integer-programming scheduler. Deliberately decoupled from the LLM and
data-fetch layers so it can be unit-tested on its own (README "golden rule").
"""

from scheduler.types import (
    Course,
    ScheduleResult,
    Section,
    SolverConfig,
    TimeSlot,
    Weights,
)

__all__ = [
    "Course",
    "ScheduleResult",
    "Section",
    "SolverConfig",
    "TimeSlot",
    "Weights",
]
