"""Advisory replies (career recommendations, explain plan) — not template dumps."""

from __future__ import annotations

from agent.advisory import advisory_reply
from agent.graph import run_turn
from agent.intent_schema import TurnUnderstanding


def test_explain_uses_advisory_not_template(monkeypatch) -> None:
    monkeypatch.setattr("agent.advisory.llm_available", lambda: True)
    monkeypatch.setattr(
        "agent.advisory.complete_text",
        lambda system, user: "For data science, lean on STAT 230/231/341 and CS 486 in upper years.",
    )
    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (TurnUnderstanding(intent="general", career_goal="data science"), True),
    )
    intake = {
        "program": "Computer Science",
        "faculty": "Math",
        "reqs_key": "CS-Major",
        "residency": "international",
        "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "data science",
    }
    plan = {
        "program": "Computer Science",
        "sequence": "math-coop",
        "start_term": "Fall 2026",
        "terms": [
            {"label": "2B", "kind": "study", "courses": ["STAT 230", "CS 246"]},
        ],
    }
    out = run_turn({
        "messages": [{"role": "user", "content": "i want you to explain"}],
        "intake": intake,
        "config": {},
        "plan": plan,
    })
    expl = out.get("explanation", "")
    assert "STAT 230" in expl or "CS 486" in expl
    assert "Agent pipeline" not in expl
    assert "Tell me to make a term lighter" not in expl
    assert out.get("llm_explained")


def test_career_advice_recommends(monkeypatch) -> None:
    monkeypatch.setattr("agent.advisory.llm_available", lambda: True)
    monkeypatch.setattr(
        "agent.advisory.complete_text",
        lambda system, user: "Take STAT 341 and CS 486 once you finish STAT 231.",
    )
    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (
            TurnUnderstanding(intent="career_advice", career_goal="data science"),
            True,
        ),
    )
    intake = {
        "program": "Computer Science",
        "faculty": "Math",
        "reqs_key": "CS-Major",
        "residency": "international",
        "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "data science",
    }
    plan = {"program": "CS", "sequence": "math-coop", "start_term": "Fall 2026", "terms": []}
    out = run_turn({
        "messages": [{"role": "user", "content": "any courses you recommend for ds?"}],
        "intake": intake,
        "plan": plan,
    })
    assert "STAT 341" in out.get("explanation", "") or "CS 486" in out.get("explanation", "")
