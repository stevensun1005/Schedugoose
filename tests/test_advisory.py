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
        # Recommendations require prereqs taken-or-planned: STAT 231 completed.
        "profile": {"completed": ["STAT 231"]},
        "rag_hits": [{"courses": ["STAT 341", "CS 486", "MATH 240"]}],  # MATH 240 not real, CS 486 in plan
    }
    text = _fallback_advisory(state)
    assert "STAT 341" in text          # real + not in plan + prereq met
    assert "MATH 240" not in text      # invented course is filtered out
    assert "CS 486" not in text        # already in the plan, not re-suggested


def test_advisory_skips_core_and_shows_prereqs() -> None:
    plan = {"terms": [{"label": "3A", "kind": "study", "courses": ["STAT 231", "CS 348"]}]}
    state = {
        "intake": {"career_goal": "data science"}, "plan": plan,
        # CS 240 is core (required) — must NOT be recommended; CS 451 is an elective
        # whose prereq (CS 348) is planned, so it stays recommendable.
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
        # Post-hoc grounding allows only plan/transcript/addable codes — the
        # mock reply references courses that are in the plan.
        lambda system, user: "For data science, STAT 230 and CS 246 set you up well.",
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
        # Prereqs of the recommended courses are on the transcript, so the
        # post-hoc grounding check accepts the reply.
        "profile": {"completed": ["CS 245", "STAT 231"]},
    })
    assert "STAT 341" in out.get("explanation", "") or "CS 486" in out.get("explanation", "")


def test_recommendations_respect_eligibility() -> None:
    # A Math Studies student who failed CS 245: CS 486 (prereq CS 245) and
    # CS 480 (CS-students-only) must never be recommended.
    from agent.advisory import _addable_courses, _catalog

    completed = ["CS 135", "CS 136", "MATH 135", "MATH 136", "STAT 230", "STAT 231"]
    state = {
        "intake": {"program": "Mathematical Studies", "faculty": "Math",
                   "completed": completed},
        "profile": {"completed": completed},
        "rag_hits": [{"courses": ["CS 486", "CS 480", "PHIL 145", "PSYCH 101"]}],
    }
    plan = {"terms": []}
    addable = _addable_courses(state, plan, _catalog())
    assert "CS 486" not in addable  # CS-only + prereq CS 245 not passed
    assert "CS 480" not in addable  # CS-only
    assert "PHIL 145" in addable    # open elective, no prereqs


def test_recommendation_prereqs_must_be_taken_or_planned() -> None:
    from agent.advisory import _addable_courses, _catalog

    # CS student without CS 245 completed or planned -> CS 486 filtered out.
    state = {
        "intake": {"program": "Computer Science", "faculty": "Math",
                   "completed": ["CS 135", "CS 136"]},
        "profile": {"completed": ["CS 135", "CS 136"]},
        "rag_hits": [{"courses": ["CS 486"]}],
    }
    assert _addable_courses(state, {"terms": []}, _catalog()) == []
    # With CS 245 + STAT 231 planned, it becomes recommendable.
    plan = {"terms": [{"courses": ["CS 245", "STAT 231"]}]}
    assert _addable_courses(state, plan, _catalog()) == ["CS 486"]


def test_fresh_plan_renders_template_not_advisory() -> None:
    # The turn that just built the plan shows the grounded term-by-term
    # template (with why-notes), never the free-text advisory pitch.
    from agent.intent_schema import TurnUnderstanding
    from agent.nodes.explain import explain

    plan = {"program": "Mathematical Studies", "sequence": "Math Regular",
            "start_term": "Fall 2026", "total_units": 20.0,
            "terms": [{"label": "4B", "display": "Fall 2026", "kind": "study",
                       "courses": ["STAT 330"], "why": "requirement → STAT 330"}]}
    state = {
        "intake": {"program": "Mathematical Studies"}, "config": {}, "plan": plan,
        "replanned": True,
        "messages": [{"role": "user", "content": "Here is my transcript — plan my remaining terms."}],
        "understanding": TurnUnderstanding(intent="career_advice").to_state_dict(),
    }
    out = explain(state)["explanation"]
    assert "term-by-term plan" in out
    assert "why: requirement → STAT 330" in out


def test_llm_reply_naming_ineligible_course_is_discarded(monkeypatch) -> None:
    # The model ignores the addable list and pitches a CS-only course to a
    # Math Studies student -> its text is discarded for the grounded fallback.
    monkeypatch.setattr("agent.advisory.llm_available", lambda: True)
    monkeypatch.setattr(
        "agent.advisory.complete_text",
        lambda system, user: "I'd recommend adding CS 492 to 1A.",
    )
    state = {
        "intake": {"program": "Mathematical Studies", "faculty": "Math",
                   "career_goal": "data analytics", "completed": ["STAT 231"]},
        "profile": {"completed": ["STAT 231"]},
        "plan": {"terms": [{"label": "4B", "kind": "study", "courses": ["STAT 330"]}]},
        "rag_hits": [{"courses": ["STAT 341"]}],
        "messages": [{"role": "user", "content": "what electives for data analytics?"}],
    }
    text, used_llm = advisory_reply(state)
    assert "CS 492" not in text
    assert used_llm is False  # fell back to the deterministic reply
