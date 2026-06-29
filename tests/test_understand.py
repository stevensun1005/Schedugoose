"""Tests for LLM-first turn understanding."""

from __future__ import annotations

from agent.intent_schema import TurnUnderstanding
from agent.nodes.gather import gather_constraints
from agent.understand import apply_understanding, wants_course_lookup


def _mock_understanding(monkeypatch, understanding: TurnUnderstanding) -> None:
    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (understanding, True),
    )


def test_llm_business_spec_electives(monkeypatch) -> None:
    _mock_understanding(monkeypatch, TurnUnderstanding(
        intent="onboarding",
        specializations=["CS-Business-Specialization"],
        suggested_electives=["ECON 101", "ENGL 119", "SPCOM 223"],
        career_goal="business",
    ))
    state = {
        "messages": [{"role": "user", "content": "i want business specilization"}],
        "intake": {
            "program": "Computer Science",
            "faculty": "Math",
            "reqs_key": "CS-Major",
            "residency": "international",
            "sequence": "math-coop",
            "start_term": {"season": "Fall", "year": 2026},
        },
    }
    out = gather_constraints(state)
    picks = out["intake"].get("elective_picks") or []
    assert "ECON 101" in picks
    assert out.get("used_llm")


def test_wants_course_lookup_from_understanding() -> None:
    state = {
        "messages": [{"role": "user", "content": "whatis soc101"}],
        "understanding": TurnUnderstanding(
            intent="course_lookup",
            course_codes=["SOC 101"],
        ).to_state_dict(),
    }
    assert wants_course_lookup(state)


def test_apply_understanding_degree_plan() -> None:
    intake = {"reqs_key": "CS-Major", "program": "Computer Science", "faculty": "Math"}
    u = TurnUnderstanding(
        intent="onboarding",
        specializations=["CS-Business-Specialization"],
    )
    out = apply_understanding(intake, u, text="business specialization")
    assert "CS-Business-Specialization" in out["degree_plan"]["specializations"]
