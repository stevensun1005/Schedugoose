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
