"""Comprehensive UW degree-requirement knowledge (majors/minors/specializations)."""

from __future__ import annotations

from agent.planner import plan_sequence
from agent.requirements_qa import format_requirements_answer, is_requirements_question
from data.degree_requirements import (
    ALL_COMPONENTS,
    SPECIALIZATION_INFO,
    describe_component,
)
from eval.checker import verify_plan

_IK = {"program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major"}


def test_all_eight_cs_specializations_present():
    names = {c.name for c in SPECIALIZATION_INFO.values()}
    for expected in (
        "Artificial Intelligence", "Bioinformatics", "Business", "Computational Fine Art",
        "Digital Hardware", "Game Design", "Human-Computer Interaction", "Computational Mathematics",
    ):
        assert expected in names


def test_every_component_cites_a_source():
    assert all(c.source for c in ALL_COMPONENTS.values())


def test_ai_specialization_lists_real_courses():
    desc = describe_component("CS-AI-Specialization")
    assert "CS 486" in desc and "CS 492" in desc and "CS 480" in desc


def test_describe_named_specialization():
    ans = format_requirements_answer("what does the game design specialization require", _IK, {"terms": []})
    assert "Game Design" in ans and "CS 488" in ans


def test_named_spec_beats_generic_list():
    ans = format_requirements_answer("what does the AI specialization require", _IK, {"terms": []})
    assert "Artificial Intelligence" in ans and "CS 486" in ans
    assert "you can add" not in ans  # not the list format


def test_list_specializations_and_minors():
    specs = format_requirements_answer("what specializations are there", _IK, {"terms": []})
    assert "Bioinformatics" in specs and "Game Design" in specs
    minors = format_requirements_answer("what minors can i take", _IK, {"terms": []})
    assert "Statistics Minor" in minors


def test_requirements_question_detected():
    assert is_requirements_question("what specializations can i take")
    assert is_requirements_question("bioinformatics specialization requirements")


def test_reference_only_specializations_flagged():
    assert describe_component("CS-Bioinformatics-Specialization").endswith
    assert "reference only" in describe_component("CS-Bioinformatics-Specialization").lower()


def test_all_specializations_keep_plans_complete():
    base = {
        **_IK, "residency": "domestic", "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026}, "career_goal": "exploring options",
    }
    for key in ("CS-Game-Design-Specialization", "CS-Digital-Hardware-Specialization",
                "CS-Bioinformatics-Specialization"):
        dp = {"kind": "major_specialization", "primary": "CS-Major",
              "specializations": [key], "minors": [], "extra_majors": []}
        plan = plan_sequence({**base, "degree_plan": dp}, {}, set(), "x")
        assert plan["complete"], key
        assert verify_plan(plan, completed=set())["all_ok"], key
