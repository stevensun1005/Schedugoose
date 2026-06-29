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


def test_career_goal_not_invented_on_other_turn() -> None:
    # Reported bug: the LLM assumed "data science" on the start-term turn even
    # though the user never stated a career. Must be rejected.
    prior = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "sequence": "math-coop",  # start_term still missing
    }
    u = TurnUnderstanding(
        intent="onboarding",
        start_term={"season": "Winter", "year": 2027},
        career_goal="data science",
    )
    out = apply_understanding(prior, u, text="winter 2027")
    assert out.get("career_goal") is None


def test_sequence_answer_not_captured_as_career() -> None:
    # Reported bug: answering "co-op" set career_goal to "co-op".
    prior = {"program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
             "residency": "domestic"}  # answering the sequence question now
    u = TurnUnderstanding(intent="onboarding", sequence="co-op", career_goal="co-op")
    out = apply_understanding(prior, u, text="co-op")
    assert out.get("career_goal") is None


def test_career_goal_accepted_when_stated() -> None:
    prior = {"program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major"}
    u = TurnUnderstanding(intent="onboarding", career_goal="data science")
    out = apply_understanding(prior, u, text="i want to be a data scientist")
    assert out.get("career_goal") == "data science"


def test_career_goal_accepted_when_it_is_the_question() -> None:
    # All other fields known → this turn is the career answer; accept a bare reply.
    prior = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
    }
    u = TurnUnderstanding(intent="onboarding", career_goal="robotics")
    out = apply_understanding(prior, u, text="robots")
    assert out.get("career_goal") == "robotics"


def test_apply_understanding_degree_plan() -> None:
    intake = {"reqs_key": "CS-Major", "program": "Computer Science", "faculty": "Math"}
    u = TurnUnderstanding(
        intent="onboarding",
        specializations=["CS-Business-Specialization"],
    )
    out = apply_understanding(intake, u, text="business specialization")
    assert "CS-Business-Specialization" in out["degree_plan"]["specializations"]
