"""Program first-year templates + recommended timelines (UW-sourced)."""

from __future__ import annotations

from agent.course_qa import gather_course_facts
from agent.planner import plan_sequence
from agent.requirements_qa import format_requirements_answer, is_requirements_question
from data.program_templates import (
    first_year_pins,
    format_first_year,
    recommended_term,
    template_for,
)

_CS_INTAKE = {
    "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
    "residency": "domestic", "sequence": "math-coop",
    "start_term": {"season": "Fall", "year": 2026}, "career_goal": "exploring options",
}


def test_cs_first_year_template_is_pinned_in_plan() -> None:
    plan = plan_sequence(_CS_INTAKE, {}, set(), "exploring options")
    one_a = next(t for t in plan["terms"] if t["label"] == "1A")["courses"]
    one_b = next(t for t in plan["terms"] if t["label"] == "1B")["courses"]
    for c in ("CS 135", "MATH 135", "MATH 137"):
        assert c in one_a
    for c in ("CS 136", "MATH 136", "MATH 138"):
        assert c in one_b


def test_first_year_pins_filtered_to_catalog() -> None:
    # SE first-year courses aren't schedulable here → no pins.
    assert first_year_pins("Software Engineering", {"CS 135"}) == {}
    assert template_for("Software Engineering").schedulable is False


def test_recommended_term_surfaced_in_qa() -> None:
    assert recommended_term("CS 246") == "2A"
    facts = gather_course_facts("CS 246", intake=_CS_INTAKE)
    assert facts.get("recommended_term") == "2A"


def test_standard_first_year_question_answered() -> None:
    assert is_requirements_question("what are the standard first year courses for CS")
    ans = format_requirements_answer("standard first year for software engineering", _CS_INTAKE, {"terms": []})
    assert "CS 137" in ans and "SE 101" in ans


def test_first_year_phrase_not_triggered_by_revision() -> None:
    assert not is_requirements_question("make 1A lighter")
    assert not is_requirements_question("no music in 1A")


def test_format_first_year_cites_source() -> None:
    text = format_first_year("Computer Science")
    assert "CS 135" in text and "uwaterloo.ca" in text
