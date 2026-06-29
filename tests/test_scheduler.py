"""Unit tests for the OR core. No LLM, no network -- pure solver behavior.

Milestone (README Phase 1): correct, conflict-free, rule-compliant schedules
with no LLM involved.
"""

from __future__ import annotations

import pytest

from scheduler.conflicts import find_conflicts
from scheduler.solve import solve
from scheduler.types import (
    Course,
    Section,
    SolverConfig,
    TimeSlot,
    Weights,
    parse_weekdays,
)


# --------------------------------------------------------------------------- #
# Mock data helpers
# --------------------------------------------------------------------------- #
def lec(course_id: str, code: str, weekdays: str, start: int, end: int, instr: str = "") -> Section:
    return Section(
        course_id=course_id,
        component="LEC",
        section_code=code,
        times=(TimeSlot(weekdays, start, end),),
        instructor=instr,
        cap=100,
        enrolled=0,
    )


def course(course_id: str, units: float, sections: list[Section], **kw) -> Course:
    return Course(course_id=course_id, title=course_id, units=units, sections=sections, **kw)


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def test_parse_weekdays_thursday_not_tuesday():
    assert parse_weekdays("TTh") == frozenset({"T", "Th"})
    assert parse_weekdays("MWF") == frozenset({"M", "W", "F"})
    assert parse_weekdays("Th") == frozenset({"Th"})


def test_timeslot_overlap():
    a = TimeSlot("MWF", 600, 660)
    b = TimeSlot("MWF", 630, 690)   # overlaps on M/W/F
    c = TimeSlot("TTh", 600, 660)   # different days
    d = TimeSlot("MWF", 660, 720)   # touches but does not overlap
    assert a.overlaps(b)
    assert not a.overlaps(c)
    assert not a.overlaps(d)


def test_find_conflicts_detects_overlap():
    a = course("CS 1", 0.5, [lec("CS 1", "LEC 001", "MWF", 600, 660)])
    b = course("CS 2", 0.5, [lec("CS 2", "LEC 001", "MWF", 630, 690)])
    conflicts = find_conflicts([a, b])
    assert len(conflicts) == 1


# --------------------------------------------------------------------------- #
# Hard constraints
# --------------------------------------------------------------------------- #
def test_no_conflict_in_solution():
    a = course("CS 1", 1.0, [lec("CS 1", "LEC 001", "MWF", 600, 660)])
    b = course("CS 2", 1.0, [lec("CS 2", "LEC 001", "MWF", 630, 690)])  # clashes with A
    c = course("CS 3", 1.0, [lec("CS 3", "LEC 001", "TTh", 600, 660)])  # clashes with neither
    config = SolverConfig(min_units=1.0, max_units=2.0)
    res = solve([a, b, c], None, config)
    assert res.feasible
    # Cannot pick both clashing courses.
    assert not ({"CS 1", "CS 2"} <= set(res.selected_courses))


def test_linking_one_section_per_component():
    sections = [
        Section("CS 486", "LEC", "LEC 001", (TimeSlot("MWF", 600, 660),), cap=100),
        Section("CS 486", "LEC", "LEC 002", (TimeSlot("TTh", 600, 660),), cap=100),
        Section("CS 486", "TUT", "TUT 101", (TimeSlot("F", 900, 960),), cap=100),
        Section("CS 486", "TUT", "TUT 102", (TimeSlot("Th", 900, 960),), cap=100),
    ]
    c = course("CS 486", 0.5, sections)
    config = SolverConfig(min_units=0.5, max_units=0.5, must_include=["CS 486"])
    res = solve([c], None, config)
    assert res.feasible
    picked = [s for s in res.selected_sections if s.course_id == "CS 486"]
    lecs = [s for s in picked if s.component == "LEC"]
    tuts = [s for s in picked if s.component == "TUT"]
    assert len(lecs) == 1 and len(tuts) == 1


def test_credit_load_bounds():
    courses = [
        course(f"CS {i}", 0.5, [lec(f"CS {i}", "LEC 001", "MWF", 600 + i * 70, 650 + i * 70)])
        for i in range(6)
    ]
    config = SolverConfig(min_units=1.5, max_units=2.0)
    res = solve(courses, None, config)
    assert res.feasible
    assert 1.5 - 1e-9 <= res.total_units <= 2.0 + 1e-9


def test_must_include_and_must_avoid():
    a = course("CS 1", 0.5, [lec("CS 1", "LEC 001", "MWF", 600, 660)])
    b = course("CS 2", 0.5, [lec("CS 2", "LEC 001", "TTh", 600, 660)])
    config = SolverConfig(
        min_units=0.5, max_units=1.0, must_include=["CS 1"], must_avoid=["CS 2"]
    )
    res = solve([a, b], None, config)
    assert res.feasible
    assert "CS 1" in res.selected_courses
    assert "CS 2" not in res.selected_courses


def test_program_requirement_coverage():
    ai = [
        course(f"CS {400 + i}", 0.5, [lec(f"CS {400 + i}", "LEC 001", "TTh", 600 + i * 70, 650 + i * 70)],
               categories=["CS-AI"])
        for i in range(3)
    ]
    other = course("MATH 1", 0.5, [lec("MATH 1", "LEC 001", "MWF", 600, 660)], categories=["MATH"])
    config = SolverConfig(min_units=1.0, max_units=2.5, program_reqs={"CS-AI": 2})
    res = solve(ai + [other], None, config)
    assert res.feasible
    ai_taken = sum(1 for c in res.selected_courses if c.startswith("CS"))
    assert ai_taken >= 2


# --------------------------------------------------------------------------- #
# Objective / soft preferences
# --------------------------------------------------------------------------- #
def test_morning_penalty_prefers_later_section():
    # Same course, two non-conflicting LEC options; one early, one late.
    sections = [
        Section("CS 9", "LEC", "LEC 001", (TimeSlot("MWF", 510, 570),), cap=100),  # 08:30
        Section("CS 9", "LEC", "LEC 002", (TimeSlot("MWF", 720, 780),), cap=100),  # 12:00
    ]
    c = course("CS 9", 0.5, sections, career_relevance=1.0)
    config = SolverConfig(
        min_units=0.5, max_units=0.5,
        weights=Weights(career=0.5, morning=0.9),
        early_before=600,
    )
    res = solve([c], None, config)
    assert res.feasible
    picked = [s.section_code for s in res.selected_sections]
    assert "LEC 002" in picked and "LEC 001" not in picked


def test_career_relevance_prefers_relevant_course():
    a = course("CS 1", 0.5, [lec("CS 1", "LEC 001", "MWF", 600, 660)], career_relevance=0.9)
    b = course("CS 2", 0.5, [lec("CS 2", "LEC 001", "MWF", 600, 660)], career_relevance=0.1)
    # They conflict, so only one fits; the relevant one should win.
    config = SolverConfig(min_units=0.5, max_units=0.5, weights=Weights(career=1.0))
    res = solve([a, b], None, config)
    assert res.feasible
    assert res.selected_courses == ["CS 1"]


# --------------------------------------------------------------------------- #
# Infeasibility diagnosis
# --------------------------------------------------------------------------- #
def test_infeasible_credit_floor_diagnosed():
    # Only 0.5 credits available but min is 2.0 -> infeasible.
    a = course("CS 1", 0.5, [lec("CS 1", "LEC 001", "MWF", 600, 660)])
    config = SolverConfig(min_units=2.0, max_units=2.5)
    res = solve([a], None, config)
    assert not res.feasible
    assert res.diagnosis
    assert any("credit" in d.lower() for d in res.diagnosis)


def test_infeasible_program_requirement_diagnosed():
    # Need 2 from CS-AI but only one exists.
    a = course("CS 486", 0.5, [lec("CS 486", "LEC 001", "TTh", 600, 660)], categories=["CS-AI"])
    config = SolverConfig(min_units=0.5, max_units=0.5, program_reqs={"CS-AI": 2})
    res = solve([a], None, config)
    assert not res.feasible
    assert any("CS-AI" in d for d in res.diagnosis)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
