"""Enrollment restrictions: "<program> students only" filtering (H6)."""

from __future__ import annotations

from data.prefilter import prefilter_candidates
from data.restrictions import restriction_from_requirements, student_eligible
from data.uw_api import fetch_courses
from scheduler.types import Course, Section, TimeSlot


def _course(cid: str, restricted: list[str] | None = None) -> Course:
    return Course(
        course_id=cid, title=cid, units=0.5, prereqs=[],
        categories=["STAT-Core", "STAT-2xx"],
        restricted_to=restricted or [],
        sections=[Section(cid, "LEC", "LEC 001", (TimeSlot("MWF", 600, 650),), cap=100)],
    )


def test_parse_only_clause() -> None:
    assert restriction_from_requirements(
        "Prereq: MATH 119 or 138; Software Eng students only."
    ) == ["Software Eng"]
    assert restriction_from_requirements(
        "Science or Knowledge Integration students only."
    ) == ["Science or Knowledge Integration"]
    assert restriction_from_requirements("Prereq: MATH 135.") == []


def test_software_eng_not_open_to_cs() -> None:
    assert student_eligible(["Software Eng"], "Computer Science", "Math") is False
    assert student_eligible(["Software Eng"], "Software Engineering", "Engineering") is True


def test_software_eng_not_open_to_general_engineering() -> None:
    # The SE program restriction must not leak to every Engineering student.
    assert student_eligible(["Software Eng"], "Mechatronics Engineering", "Engineering") is False
    # A faculty-level "Engineering students only" course still admits them.
    assert student_eligible(["Engineering"], "Mechatronics Engineering", "Engineering") is True


def test_open_and_unknown_student() -> None:
    assert student_eligible([], "Computer Science", "Math") is True
    # Unknown student (mid-onboarding) — don't over-filter restricted courses.
    assert student_eligible(["Software Eng"], None, None) is True


def test_prefilter_drops_restricted_course_for_cs() -> None:
    courses = [_course("STAT 231"), _course("STAT 206", restricted=["Software Eng"])]
    out = prefilter_candidates(
        courses, completed=set(), slot_label="2B",
        program="Computer Science", faculty="Math",
    )
    ids = {c.course_id for c in out}
    assert "STAT 231" in ids
    assert "STAT 206" not in ids


def test_mock_catalog_stat206_is_restricted() -> None:
    by_id = {c.course_id: c for c in fetch_courses()}
    assert by_id["STAT 206"].restricted_to  # tagged Software Eng only
    # And it is filtered out for a CS student at the term it would otherwise fit.
    eligible = prefilter_candidates(
        list(by_id.values()), completed={"MATH 135"}, slot_label="2B",
        program="Computer Science", faculty="Math",
    )
    assert "STAT 206" not in {c.course_id for c in eligible}
