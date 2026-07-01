"""Kuali requirement text -> solver constraints (the live-requirements path)."""

from __future__ import annotations

from data.requirements_compiler import (
    ReqGroup,
    compile_requirements,
    remaining_from_groups,
    tag_catalog,
)

# Structure mirrors the real Kuali payload for Mathematical Studies (public
# calendar data).
_KUALI_TEXT = """Required Courses
Complete all of the following
Complete 1 of the following: CS115 - Introduction to Computer Science 1 (0.50) CS135 - Designing Functional Programs (0.50) CS145 - Designing Functional Programs (Advanced Level) (0.50)
Complete 1 of the following: MATH225 - Applied Linear Algebra 2 (0.50) MATH235 - Linear Algebra 2 for Honours Mathematics (0.50) MATH245 - Linear Algebra 2 (Advanced Level) (0.50)
Complete 1 of the following: STAT220 - Probability (Non-Specialist Level) (0.50) STAT230 - Probability (0.50) STAT240 - Probability (Advanced Level) (0.50)
Complete 10 additional math courses at the 300- or 400-level from the following subject codes: ACTSC, AMATH, CO, CS, MATBUS, MATH, PMATH, STAT See Bachelor of Mathematics degree-level requirements . Mathematical Studies students are exempt from taking the List A courses.
Complete a minimum of 13.0 units of math courses.
"""


def test_compiles_choice_and_level_groups() -> None:
    groups = compile_requirements(_KUALI_TEXT)
    assert len(groups) == 4  # 3 choice groups + 1 level rule (units line skipped)
    choice = groups[0]
    assert choice.count == 1 and "CS 135" in choice.courses and "CS 145" in choice.courses
    level = groups[-1]
    assert level.count == 10 and level.min_level == 300
    # Trailing prose ("STAT See Bachelor of…") must not corrupt the subjects.
    assert "STAT" in level.subjects and "MATH" in level.subjects
    assert all(s.isalpha() for s in level.subjects)


def test_non_honours_option_satisfies_choice_group() -> None:
    # A student who took MATH 225 (not 235) has the linear-algebra-2 slot done.
    groups = compile_requirements(_KUALI_TEXT)
    remaining = remaining_from_groups(groups, {"CS 135", "MATH 225", "STAT 230"})
    assert not any("MATH 225" in k for k in remaining)  # group satisfied
    assert len(remaining) == 1  # only the 300+-level rule remains


def test_level_rule_counts_all_math_faculty_subjects() -> None:
    groups = compile_requirements(_KUALI_TEXT)
    level = groups[-1]
    done = {"STAT 341", "STAT 442", "CS 330", "CS 338", "CO 327", "STAT 337"}
    assert level.satisfied_by(done) == 6
    assert level.satisfied_by({"MATH 235", "STAT 230"}) == 0  # 2xx don't count


def test_tag_catalog_marks_matching_courses() -> None:
    from data.uw_api import fetch_courses

    groups = compile_requirements(_KUALI_TEXT)
    catalog = fetch_courses()
    tag_catalog(groups, catalog)
    by_id = {c.course_id: c for c in catalog}
    level_label = groups[-1].label
    assert level_label in by_id["STAT 330"].categories
    assert level_label in by_id["CO 487"].categories
    assert level_label not in by_id["MATH 235"].categories


def test_round_trip_serialization() -> None:
    groups = compile_requirements(_KUALI_TEXT)
    for g in groups:
        assert ReqGroup.from_dict(g.to_dict()) == g
