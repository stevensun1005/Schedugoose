"""Term-specific course placement (e.g. CS 245 + 246 in 2A)."""

from __future__ import annotations

from agent.planner import plan_sequence
from agent.semantic import rule_based_config


def _sample_intake() -> dict:
    return {
        "program": "Computer Science",
        "faculty": "Math",
        "reqs_key": "CS-Major",
        "residency": "international",
        "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "data science",
        "elective_picks": [],
    }


def test_parse_cs245_246_in_2a() -> None:
    cfg = rule_based_config("i want to take cs245 and 246 in 2a", "CS-Major", None)
    assert "2A" in cfg["term_requirements"]
    assert "CS 245" in cfg["term_requirements"]["2A"]
    assert "CS 246" in cfg["term_requirements"]["2A"]


def test_plan_honors_2a_pins() -> None:
    intake = _sample_intake()
    config = rule_based_config("i want to take cs245 and 246 in 2a", "CS-Major", {})
    plan = plan_sequence(intake, config, set(), "data science")
    term_2a = next(t for t in plan["terms"] if t["label"] == "2A")
    assert "CS 245" in term_2a["courses"], term_2a["courses"]
    assert "CS 246" in term_2a["courses"], term_2a["courses"]


def test_parse_add_to_term_connectors() -> None:
    # "add X to 3B" / "move X into 2A" — the "to"/"into" connectors must pin
    # the course, same as "in"/"for". Regression: these were silently dropped.
    cfg = rule_based_config("add PHIL 145 to 3B", "CS-Major", None)
    assert cfg["term_requirements"].get("3B") == ["PHIL 145"], cfg["term_requirements"]
    cfg = rule_based_config("move CS 246 into 2A", "CS-Major", None)
    assert "CS 246" in cfg["term_requirements"].get("2A", []), cfg["term_requirements"]


def test_plan_honors_add_to_term() -> None:
    intake = _sample_intake()
    config = rule_based_config("add PHIL 145 to 3B", "CS-Major", {})
    plan = plan_sequence(intake, config, set(), "data science")
    term_3b = next(t for t in plan["terms"] if t["label"] == "3B")
    assert "PHIL 145" in term_3b["courses"], term_3b["courses"]


def test_avoid_cs240_add_math237_in_2a() -> None:
    prev = {"term_requirements": {"2A": ["CS 245", "CS 246"]}}
    cfg = rule_based_config(
        "i dont want to take cs240 in 2a, want math237 instead",
        "CS-Major",
        prev,
    )
    assert "CS 240" in cfg["term_avoid"]["2A"]
    assert "MATH 237" in cfg["term_requirements"]["2A"]


def test_avoid_eng_in_2a() -> None:
    prev = {"term_requirements": {"2A": ["CS 245", "CS 246"]}, "elective_picks": ["ENGL 119"]}
    cfg = rule_based_config(
        "i dont want to take engl in 2a, i want to take cs246 instead",
        "CS-Major",
        prev,
    )
    assert "ENGL 119" in cfg["term_avoid"]["2A"]
    assert "CS 246" in cfg["term_requirements"]["2A"]


def test_plan_no_engl_in_2a() -> None:
    intake = _sample_intake()
    intake["elective_picks"] = ["ENGL 119", "ECON 101"]
    prev = {"term_requirements": {"2A": ["CS 245", "CS 246"]}}
    config = rule_based_config(
        "i dont want to take engl in 2a, i want to take cs246 instead",
        "CS-Major",
        prev,
    )
    plan = plan_sequence(intake, config, set(), "data science")
    term_2a = next(t for t in plan["terms"] if t["label"] == "2A")
    assert "ENGL 119" not in term_2a["courses"], term_2a["courses"]
    assert "CS 246" in term_2a["courses"], term_2a["courses"]


def test_plan_swaps_out_cs240_for_math237() -> None:
    intake = _sample_intake()
    prev = {"term_requirements": {"2A": ["CS 245", "CS 246"]}}
    config = rule_based_config(
        "i dont want to take cs240 in 2a, want math237 instead",
        "CS-Major",
        prev,
    )
    plan = plan_sequence(intake, config, set(), "data science")
    term_2a = next(t for t in plan["terms"] if t["label"] == "2A")
    assert "CS 240" not in term_2a["courses"], term_2a["courses"]
    assert "MATH 237" in term_2a["courses"], term_2a["courses"]
