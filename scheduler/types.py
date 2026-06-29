"""Core domain types for Schedugoose.

API responses are normalized into these objects. Times are stored as *minutes
since midnight* so that detecting a clash between two sections reduces to a
simple interval-overlap check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Canonical weekday tokens used throughout the codebase.
WEEKDAY_TOKENS: tuple[str, ...] = ("M", "T", "W", "Th", "F", "Sa", "Su")


def parse_weekdays(weekdays: str) -> frozenset[str]:
    """Parse a compact weekday string (e.g. ``"TTh"``, ``"MWF"``) into tokens.

    "Th" must be matched before "T" so that Thursday is not read as Tuesday.
    """

    tokens: list[str] = []
    i = 0
    while i < len(weekdays):
        if weekdays[i:i + 2] in ("Th", "Sa", "Su"):
            tokens.append(weekdays[i:i + 2])
            i += 2
        elif weekdays[i] in ("M", "T", "W", "F"):
            tokens.append(weekdays[i])
            i += 1
        else:
            # Skip separators / unknown characters.
            i += 1
    return frozenset(tokens)


def minutes_to_hhmm(minutes: int) -> str:
    """Render minutes-since-midnight as ``HH:MM``."""

    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def hhmm_to_minutes(hhmm: str) -> int:
    """Parse ``"HH:MM"`` into minutes since midnight."""

    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


@dataclass(frozen=True)
class TimeSlot:
    """A meeting block within a week."""

    weekdays: str       # "TTh", "MWF"
    start: int          # minutes since midnight, e.g. 16:00 -> 960
    end: int            # minutes since midnight

    @property
    def days(self) -> frozenset[str]:
        return parse_weekdays(self.weekdays)

    def overlaps(self, other: "TimeSlot") -> bool:
        """Two slots clash iff they share a weekday and their intervals overlap."""

        if self.days.isdisjoint(other.days):
            return False
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Section:
    """A specific offering of a course component (LEC/TUT/LAB)."""

    course_id: str          # "CS 486"
    component: str          # "LEC" | "TUT" | "LAB"
    section_code: str       # "LEC 001"
    times: tuple[TimeSlot, ...]
    instructor: str = ""
    term: str = ""
    cap: int = 0
    enrolled: int = 0

    @property
    def id(self) -> str:
        """Stable, unique identifier used as the CP-SAT variable name."""

        return f"{self.course_id}|{self.section_code}".replace(" ", "_")

    @property
    def has_space(self) -> bool:
        return self.cap <= 0 or self.enrolled < self.cap

    def conflicts_with(self, other: "Section") -> bool:
        return any(a.overlaps(b) for a in self.times for b in other.times)


@dataclass
class Course:
    """A course and all of its candidate sections for a term."""

    course_id: str
    title: str
    units: float
    prereqs: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    career_relevance: float = 0.0   # 0-1, computed per target career
    easiness: float = 0.0           # 0-1, workload signal (higher = lighter)
    prof_rating: float = 0.0        # 0-1, instructor-quality signal
    categories: list[str] = field(default_factory=list)  # program / KB tags
    # Enrollment restrictions parsed from "<program> students only" clauses.
    # Empty = open to everyone. Pre-filtering drops courses a student isn't
    # eligible for (e.g. STAT 206 is "Software Eng students only").
    restricted_to: list[str] = field(default_factory=list)

    def components(self) -> list[str]:
        """Distinct component types present among this course's sections."""

        seen: list[str] = []
        for s in self.sections:
            if s.component not in seen:
                seen.append(s.component)
        return seen

    def sections_of(self, component: str) -> list[Section]:
        return [s for s in self.sections if s.component == component]


@dataclass
class Weights:
    """Objective weights produced by the LLM semantic layer."""

    career: float = 0.5
    easy: float = 0.3
    prof: float = 0.2
    morning: float = 0.0   # penalty for early sections
    friday: float = 0.0    # penalty for Friday sections
    gap: float = 0.0        # penalty for fragmented days (optional)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Weights":
        data = data or {}
        return cls(
            career=float(data.get("career", 0.5)),
            easy=float(data.get("easy", 0.3)),
            prof=float(data.get("prof", 0.2)),
            morning=float(data.get("morning", 0.0)),
            friday=float(data.get("friday", 0.0)),
            gap=float(data.get("gap", 0.0)),
        )


@dataclass
class SolverConfig:
    """Everything the solver needs beyond the candidate course list.

    This is exactly the structured object the LLM semantic layer emits.
    """

    min_units: float = 2.0
    max_units: float = 2.5
    weights: Weights = field(default_factory=Weights)
    # Earliest acceptable start (minutes since midnight). Sections starting
    # before this are treated as "early" for the morning penalty.
    early_before: int = 600          # 10:00
    avoid_friday: bool = False
    must_include: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    # Program requirement coverage: category -> minimum number of courses.
    program_reqs: dict[str, int] = field(default_factory=dict)
    target_categories: list[str] = field(default_factory=list)
    # Workload balancing: require at least this many "easy" courses.
    min_easy_courses: int = 0
    easy_threshold: float = 0.7

    @classmethod
    def from_dict(cls, data: dict) -> "SolverConfig":
        credit = data.get("credit_load", {}) or {}
        time_prefs = data.get("time_prefs", {}) or {}
        early = time_prefs.get("avoid_before")
        early_min = hhmm_to_minutes(early) if isinstance(early, str) else 600
        return cls(
            min_units=float(credit.get("min", 2.0)),
            max_units=float(credit.get("max", 2.5)),
            weights=Weights.from_dict(data.get("weights")),
            early_before=early_min,
            avoid_friday=bool(time_prefs.get("avoid_friday", False)),
            must_include=list(data.get("must_include", [])),
            must_avoid=list(data.get("must_avoid", [])),
            program_reqs=dict(data.get("program_reqs", {})),
            target_categories=list(data.get("target_categories", [])),
            min_easy_courses=int(data.get("min_easy_courses", 0)),
            easy_threshold=float(data.get("easy_threshold", 0.7)),
        )


@dataclass
class ScheduleResult:
    """Output of a solve: the picked schedule plus solver metadata."""

    feasible: bool
    status: str
    selected_sections: list[Section] = field(default_factory=list)
    selected_courses: list[str] = field(default_factory=list)
    total_units: float = 0.0
    objective: float = 0.0
    # Populated only when infeasible: human-readable diagnosis lines.
    diagnosis: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "status": self.status,
            "total_units": round(self.total_units, 2),
            "objective": round(self.objective, 4),
            "courses": self.selected_courses,
            "sections": [
                {
                    "course_id": s.course_id,
                    "section_code": s.section_code,
                    "component": s.component,
                    "instructor": s.instructor,
                    "times": [
                        {
                            "weekdays": t.weekdays,
                            "start": minutes_to_hhmm(t.start),
                            "end": minutes_to_hhmm(t.end),
                        }
                        for t in s.times
                    ],
                }
                for s in self.selected_sections
            ],
            "diagnosis": self.diagnosis,
        }


def iter_sections(courses: Iterable[Course]) -> Iterable[Section]:
    for c in courses:
        yield from c.sections
