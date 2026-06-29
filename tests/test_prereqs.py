"""Prerequisite parsing from UW requirementsDescription text.

Mirrors UWFlow's importer: a subject stated once carries across a list of
numbers ("One of CS 240, 245, 246"), and "One of ..." is an OR-list.
"""

from __future__ import annotations

from data.prereqs import expand_course_codes, prereqs_from_requirements


def test_expand_shared_subject_across_list() -> None:
    assert expand_course_codes("One of CS 240, 245, 246") == ["CS 240", "CS 245", "CS 246"]
    assert expand_course_codes("MATH 135/137") == ["MATH 135", "MATH 137"]


def test_connector_words_not_read_as_subjects() -> None:
    # "and"/"of"/"One" must not be treated as a subject for the bare number.
    assert expand_course_codes("CS 245 and 246") == ["CS 245", "CS 246"]


def test_one_of_is_an_or_list() -> None:
    # A strict-AND planner should require only the first alternative.
    assert prereqs_from_requirements("Prereq: One of CS 240, 245, 246") == ["CS 240"]


def test_and_list_keeps_all() -> None:
    assert prereqs_from_requirements("Prereq: CS 245 and CS 246") == ["CS 245", "CS 246"]
    assert prereqs_from_requirements("Prereq: CS 240, 245") == ["CS 240", "CS 245"]


def test_first_or_branch_and_strips_restriction() -> None:
    assert prereqs_from_requirements(
        "Prereq: MATH 119 or 138; Software Eng students only."
    ) == ["MATH 119"]


def test_lab_suffix_dropped() -> None:
    assert prereqs_from_requirements("Prereq: CS 136L") == ["CS 136"]


def test_empty() -> None:
    assert prereqs_from_requirements("") == []
    assert prereqs_from_requirements(None) == []
