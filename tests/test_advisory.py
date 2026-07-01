"""Advisory replies (career recommendations, explain plan) — not template dumps."""

from __future__ import annotations

from agent.advisory import _fallback_advisory, advisory_reply
from agent.graph import run_turn
from agent.intent_schema import TurnUnderstanding


def test_no_career_does_not_assume_data_science() -> None:
    # Reported bug: advisory pushed "data science" with no stated goal.
    plan = {"terms": [{"label": "4A", "kind": "study", "courses": ["CS 486", "CS 480"]}]}
    text = _fallback_advisory({"intake": {"career_goal": "exploring options"}, "plan": plan, "rag_hits": []})
    # It must not assume DS is the goal — it should say none was given and invite one.
    assert "haven't told me" in text.lower() and "specific career" in text.lower()


def test_advisory_only_suggests_real_courses_not_in_plan() -> None:
    plan = {"terms": [{"label": "4A", "kind": "study", "courses": ["CS 486"]}]}
    state = {
        "intake": {"career_goal": "data science"}, "plan": plan,
        "rag_hits": [{"courses": ["STAT 341", "CS 486", "MATH 240"]}],  # MATH 240 not real, CS 486 in plan
    }
    text = _fallback_advisory(state)
    assert "STAT 341" in text          # real + not in plan
    assert "MATH 240" not in text      # invented course is filtered out
    assert "CS 486" not in text        # already in the plan, not re-suggested


def test_advisory_skips_core_and_shows_prereqs() -> None:
    plan = {"terms": [{"label": "3A", "kind": "study", "courses": ["STAT 231"]}]}
    state = {
        "intake": {"career_goal": "data science"}, "plan": plan,
        # CS 240 is core (required) — must NOT be recommended; CS 451 is an elective.
        "rag_hits": [{"courses": ["CS 240", "CS 451", "STAT 341"]}],
    }
    text = _fallback_advisory(state)
    assert "CS 240" not in text                 # core/required is never "recommended"
    assert "CS 451" in text and "prereq" in text.lower()   # elective, with its prereq
    assert "CS 348" in text                     # CS 451's prerequisite is shown


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
