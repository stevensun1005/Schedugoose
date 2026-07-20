"""Elective auto-inference from natural-language intent."""

from __future__ import annotations

from agent.intake import apply_elective_inference, fill_intake_offline, is_complete
from agent.nodes.gather import gather_constraints
from data.degree_plans import parse_degree_plan
from data.electives import infer_elective_picks_fallback


def test_business_spec_typo_infers_electives() -> None:
    intake = {
        "program": "Computer Science",
        "faculty": "math",
        "reqs_key": "CS-Major",
        "residency": "international",
        "sequence": "co-op",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "data science",
    }
    text = "i want to have business specilization"
    config = {"min_easy_courses": 1}

    intake = fill_intake_offline(intake, text)
    intake = apply_elective_inference(intake, text, config)

    assert intake.get("degree_plan")
    assert "CS-Business-Specialization" in intake["degree_plan"]["specializations"]
    picks = intake.get("elective_picks") or []
    assert "ECON 101" in picks
    assert "ENGL 119" in picks
    assert "MUSIC 116" not in picks


def test_infer_without_blocking_menu() -> None:
    intake = {
        "program": "Computer Science",
        "reqs_key": "CS-Major",
        "residency": "domestic",
        "sequence": "co-op",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "keep it light",
    }
    out = apply_elective_inference(intake, "business specialization please", {"min_easy_courses": 1})
    assert out.get("elective_picks")
    assert is_complete(out, {"min_easy_courses": 1})


def test_gather_business_spec_plans() -> None:
    state = {
        "messages": [{"role": "user", "content": "i want business specilization"}],
        "intake": {
            "program": "Computer Science",
            "faculty": "math",
            "reqs_key": "CS-Major",
            "residency": "international",
            "sequence": "co-op",
            "start_term": {"season": "Fall", "year": 2026},
            "career_goal": "data science",
        },
        "config": {"min_easy_courses": 1},
    }
    out = gather_constraints(state)
    assert not out.get("needs_clarification") or "Pick the electives" not in (out.get("clarification") or "")
    picks = out["intake"].get("elective_picks") or []
    assert any(c in picks for c in ("ECON 101", "ENGL 119", "SPCOM 223"))


def test_infer_elective_picks_ai() -> None:
    from data.degree_plans import plan_to_dict

    parsed = parse_degree_plan("AI specialization", "CS-Major")
    assert parsed
    picks = infer_elective_picks_fallback(
        {"reqs_key": "CS-Major", "degree_plan": plan_to_dict(parsed)},
        "AI specialization",
        {},
    )
    assert picks
    assert "CS 486" in picks or "STAT 341" in picks
