"""Returning student: start the plan at their current term, not 1A."""

from __future__ import annotations

from agent.intake import parse_entering_term
from agent.planner import plan_sequence
from agent.semantic import rule_based_config


def _intake(**over):
    base = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "sequence": "math-coop",
        "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "ai", "elective_picks": [],
    }
    base.update(over)
    return base


def test_parse_entering_term() -> None:
    assert parse_entering_term("I am a CS student going into 2B") == "2B"
    assert parse_entering_term("entering 3a next term") == "3A"
    assert parse_entering_term("I'm a 2B student") == "2B"
    assert parse_entering_term("currently in 4B") == "4B"
    # Ordinal years map to the A term of that year.
    assert parse_entering_term("im a 4th year student") == "4A"
    assert parse_entering_term("final year") == "4A"
    assert parse_entering_term("I am in year 3") == "3A"
    assert parse_entering_term("first year cs") == "1A"  # 1A == new student, harmless
    # Not an entering-term statement.
    assert parse_entering_term("make 2A lighter") is None
    assert parse_entering_term("starting Fall 2026") is None


def test_default_new_student_starts_at_1a() -> None:
    plan = plan_sequence(_intake(), rule_based_config("plan", "CS-Major", None), set(), "ai")
    assert plan["terms"][0]["label"] == "1A"
    assert plan["terms"][0]["display"] == "Fall 2026"


def test_returning_student_starts_at_entering_term() -> None:
    completed = {
        "CS 135", "CS 136", "CS 240", "CS 241", "CS 245",
        "MATH 135", "MATH 136", "MATH 137", "MATH 138", "MATH 235",
        "MATH 237", "MATH 239", "ENGL 119", "SPCOM 223", "STAT 230",
    }
    intake = _intake(start_term={"season": "Winter", "year": 2026},
                     standing="returning", entering_term="2B")
    plan = plan_sequence(intake, rule_based_config("plan", "CS-Major", None), completed, "ai")
    # First emitted study term is the entering term at the given calendar date.
    first_study = next(t for t in plan["terms"] if t["kind"] == "study")
    assert first_study["label"] == "2B"
    assert first_study["display"] == "Winter 2026"
    # No 1A/1B/2A slots are emitted (already completed).
    labels = [t["label"] for t in plan["terms"]]
    assert "1A" not in labels and "2A" not in labels
    assert plan.get("complete") is True


def test_understanding_extracts_year_and_transcript() -> None:
    from agent.intent_schema import TurnUnderstanding
    from agent.understand import apply_understanding

    u = TurnUnderstanding(entering_term="4th year",
                          completed_courses=["cs135", "MATH 135"])
    assert u.entering_term == "4A"
    out = apply_understanding({"program": "Computer Science"}, u, text="im a 4th year student")
    assert out["entering_term"] == "4A"
    assert out["standing"] == "returning"
    assert "CS 135" in out["completed"] and "MATH 135" in out["completed"]


def test_returning_student_asked_for_transcript_not_1a() -> None:
    from agent.intake import next_question

    q = next_question({"program": "Computer Science", "standing": "returning",
                       "entering_term": "4A"})
    assert "transcript" in q.lower() or "completed" in q.lower()
    assert "1A" not in q  # never ask a 4th-year about their "1A"


def test_first_year_is_not_returning() -> None:
    from agent.intent_schema import TurnUnderstanding
    from agent.understand import apply_understanding

    u = TurnUnderstanding(entering_term="first year")
    out = apply_understanding({"program": "Computer Science"}, u, text="first year cs")
    assert out.get("standing") != "returning"


def _math_studies_intake() -> dict:
    return {
        "program": "Mathematical Studies", "faculty": "Math",
        "reqs_key": "MathStudies-Major", "residency": None,
        "sequence": "math-regular", "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "exploring options", "standing": "returning",
        "entering_term": "4B", "units_earned": 19.25, "elective_picks": [],
    }


# Mirrors a real Quest transcript: MATH 225 (not 235) and MATH 237 taken,
# CS 245/246 failed (not completed), currently a Mathematical Studies student.
_TAKEN = {
    "CS 135", "CS 136", "CS 251", "CS 200", "CS 234", "CS 330", "CS 338",
    "MATH 135", "MATH 136", "MATH 137", "MATH 138", "MATH 225", "MATH 237",
    "STAT 230", "STAT 231", "STAT 341", "CO 250", "ANTH 100", "ENGL 119",
}


def test_antireq_of_taken_course_never_scheduled() -> None:
    from agent.semantic import rule_based_config

    plan = plan_sequence(_math_studies_intake(),
                         rule_based_config("plan", "MathStudies-Major", None),
                         set(_TAKEN), "exploring options")
    sched = {c for t in plan["terms"] for c in t.get("courses", [])}
    # MATH 225 was taken -> MATH 235/245 blocked; MATH 237 taken -> 247 blocked.
    assert not sched & {"MATH 235", "MATH 245", "MATH 247"}, sched


def test_cs_major_courses_blocked_for_non_cs_program() -> None:
    from agent.semantic import rule_based_config

    plan = plan_sequence(_math_studies_intake(),
                         rule_based_config("plan", "MathStudies-Major", None),
                         set(_TAKEN), "exploring options")
    sched = {c for t in plan["terms"] for c in t.get("courses", [])}
    assert "CS 240" not in sched, sched
    assert not {c for c in sched if c in {"CS 341", "CS 348", "CS 486", "CS 480"}}, sched


def test_math_studies_requires_300_level_depth() -> None:
    from data.degree_plans import MAJORS

    assert MAJORS["MathStudies-Major"]["Math-3xx"] >= 3
    # And the catalog tags Math-faculty 300+ courses with that category.
    from data.uw_api import fetch_courses

    cat = {c.course_id: c for c in fetch_courses()}
    assert "Math-3xx" in cat["STAT 330"].categories
    assert "Math-3xx" in cat["CO 487"].categories
    assert "Math-3xx" not in cat["MATH 235"].categories  # 2xx


def test_cs_student_still_eligible_for_cs_core() -> None:
    # The restriction must not break the main CS flow.
    from agent.semantic import rule_based_config

    intake = _intake()
    plan = plan_sequence(intake, rule_based_config("plan", "CS-Major", None), set(), "ai")
    sched = {c for t in plan["terms"] for c in t.get("courses", [])}
    assert "CS 240" in sched
