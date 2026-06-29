"""Tests for course-info Q&A detection and lookup."""

from __future__ import annotations

from agent.course_qa import (
    answer_course_question,
    gather_course_facts,
    is_course_info_question,
)
from data.uw_api import lookup_course


def test_is_course_info_question_positive() -> None:
    assert is_course_info_question("what is soc101")
    assert is_course_info_question("whatis soc101")
    assert is_course_info_question("soc101")
    assert is_course_info_question("Tell me about CS 486")
    assert is_course_info_question("describe STAT 230")


def test_is_course_info_question_negative() -> None:
    assert not is_course_info_question("make my plan lighter")
    assert not is_course_info_question("what courses do I need for business specialization")
    assert not is_course_info_question("hello")


def test_lookup_course_mock_soc101() -> None:
    facts = lookup_course("SOC 101")
    assert facts["course_id"] == "SOC 101"
    assert "Sociology" in facts["title"]
    assert facts.get("description") or facts.get("title")


def test_gather_course_facts_plan_term() -> None:
    plan = {
        "terms": [
            {"label": "1B", "display": "Winter 2027", "courses": ["SOC 101", "CS 136"]},
        ],
    }
    facts = gather_course_facts("soc101", plan=plan)
    assert facts["plan_term"] == "1B (Winter 2027)"


def test_course_qa_before_intake_complete() -> None:
    from agent.graph import run_turn

    state = {
        "messages": [{"role": "user", "content": "whatis soc101"}],
        "intake": {},
        "config": {},
    }
    out = run_turn(state)
    assert "SOC 101" in out.get("explanation", "")
    assert "program" not in out.get("explanation", "").lower()


def test_answer_course_question_template_fallback(monkeypatch) -> None:
    monkeypatch.setattr("agent.course_qa.complete_text", lambda *a, **k: None)
    facts = gather_course_facts("SOC 101")
    text, used = answer_course_question("what is soc101", facts)
    assert not used
    assert "SOC 101" in text
    assert "Sociology" in text
