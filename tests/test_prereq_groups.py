"""OR-aware prerequisites: 'MATH 136 or 146' is satisfied by either option."""

from __future__ import annotations

from data.prefilter import prereqs_met
from data.prereqs import prereq_groups_from_requirements
from data.uw_api import fetch_courses
from scheduler.types import Course


def test_parser_builds_and_of_or_groups() -> None:
    g = prereq_groups_from_requirements("Prereq: CS 240 and (STAT 206 or STAT 231)")
    assert ["CS 240"] in g
    assert any(set(x) >= {"STAT 206", "STAT 231"} for x in g)

    g = prereq_groups_from_requirements("Prereq: One of MATH 106, 136, 146; MATH 135")
    assert any(set(x) == {"MATH 106", "MATH 136", "MATH 146"} for x in g)
    assert ["MATH 135"] in g

    g = prereq_groups_from_requirements("Prereq: MATH 128/138/148")
    assert g == [["MATH 128", "MATH 138", "MATH 148"]]


def test_prereqs_met_honours_alternatives() -> None:
    c = Course(course_id="X 300", title="", units=0.5,
               prereqs=["CS 136"], prereq_groups=[["CS 136", "CS 146"]])
    assert prereqs_met(c, {"CS 146"})          # advanced-stream option counts
    assert prereqs_met(c, {"CS 136"})
    assert not prereqs_met(c, {"CS 135"})
    # No groups -> flat list is an AND.
    c2 = Course(course_id="Y 300", title="", units=0.5, prereqs=["A 1", "B 2"])
    assert not prereqs_met(c2, {"A 1"})
    assert prereqs_met(c2, {"A 1", "B 2"})


def test_advanced_stream_student_eligible_in_catalog() -> None:
    # A student who took CS 146 / MATH 146 (advanced first year) can take the
    # 2A core — the flat first-option prereq used to wrongly filter them out.
    by = {c.course_id: c for c in fetch_courses()}
    advanced = {"CS 145", "CS 146", "MATH 145", "MATH 146", "MATH 147", "MATH 148"}
    for cid in ("CS 240", "CS 245", "CS 246", "MATH 239", "STAT 230"):
        assert prereqs_met(by[cid], advanced), cid
    # MATH 235's alternatives come from its requirements_description parse.
    assert prereqs_met(by["MATH 235"], {"MATH 146"})


def test_fall_only_course_not_planned_in_spring(monkeypatch) -> None:
    from agent.planner import plan_sequence
    from agent.semantic import rule_based_config

    # Pretend STAT 334 is offered in Fall only.
    monkeypatch.setattr(
        "data.uw_api.offered_seasons_map",
        lambda start=None: {"STAT 334": {"Fall"}},
    )
    intake = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "sequence": "math-regular",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "ds", "elective_picks": [],
    }
    plan = plan_sequence(intake, rule_based_config("plan", "CS-Major", None), set(), "ds")
    for t in plan["terms"]:
        if t.get("kind") == "study" and "STAT 334" in (t.get("courses") or []):
            assert t["season"] == "Fall", (t["label"], t["season"])
