"""Career shorthand + UW prereq parsing tests."""

from __future__ import annotations

from agent.career import parse_career_goal
from agent.nodes.gather import gather_constraints
from data.prereqs import prereqs_from_requirements


def test_ds_maps_to_data_science() -> None:
    intake = {
        "program": "Computer Science",
        "residency": "international",
        "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
    }
    assert parse_career_goal("ds", intake) == "data science"


def test_gather_ds_completes_intake(monkeypatch) -> None:
    from agent.intent_schema import TurnUnderstanding

    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (
            TurnUnderstanding(intent="onboarding", career_goal="data science"),
            True,
        ),
    )
    state = {
        "messages": [{"role": "user", "content": "ds"}],
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
    assert out["intake"].get("career_goal") == "data science"
    assert out.get("llm_understood")
    assert not out.get("needs_clarification")


def test_gather_arbitrary_career_via_llm(monkeypatch) -> None:
    from agent.intent_schema import TurnUnderstanding

    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (
            TurnUnderstanding(intent="onboarding", career_goal="quantitative trading"),
            True,
        ),
    )
    state = {
        "messages": [
            {"role": "assistant", "content": "What career are you aiming for?"},
            {"role": "user", "content": "i wanna do prop trading at a hedge fund"},
        ],
        "intake": {
            "program": "Computer Science",
            "faculty": "Math",
            "reqs_key": "CS-Major",
            "residency": "domestic",
            "sequence": "math-coop",
            "start_term": {"season": "Fall", "year": 2026},
        },
    }
    out = gather_constraints(state)
    assert "trading" in out["intake"].get("career_goal", "").lower()
    assert out.get("llm_understood")


def test_prereqs_from_uw_cs246() -> None:
    desc = (
        "Prereq: (CS 146 and CS 136L) or (a grade of 60% or higher in CS 138) "
        "or (CS 136L and a grade of 60% or higher in CS 136); Honours Mathematics students only."
    )
    prereqs = prereqs_from_requirements(desc)
    assert "CS 146" in prereqs
    assert "CS 136" in prereqs
