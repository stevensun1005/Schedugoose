"""New vs returning student: transcript capture and plan trimming."""

from __future__ import annotations

from agent.graph import run_turn
from agent.intake import parse_standing


def test_parse_standing_new() -> None:
    assert parse_standing("i'm a brand new first year")[0] == "new"
    assert parse_standing("first year cs")[0] == "new"


def test_parse_standing_transcript() -> None:
    standing, codes = parse_standing("i've already taken CS 135, MATH 135, MATH 137")
    assert standing == "returning"
    assert codes == ["CS 135", "MATH 135", "MATH 137"]


def test_parse_standing_ignores_non_transcript() -> None:
    # Asking about / wanting a course is not a completed-course statement.
    assert parse_standing("what is CS 246") == (None, [])
    assert parse_standing("i want to take CS 246 in 2A") == (None, [])


def _run(turns: list[str]) -> dict:
    state = {"messages": [], "profile": {"completed": []}}
    for m in turns:
        state["messages"].append({"role": "user", "content": m})
        state = run_turn(state)
        state["messages"].append({"role": "assistant", "content": state.get("explanation", "")})
    return state


def test_returning_student_skips_completed_and_hits_target() -> None:
    state = _run([
        "i am in computer science",
        "i've already taken CS 135, MATH 135",
        "domestic", "math co-op", "Fall 2026", "backend engineer",
    ])
    assert state["intake"].get("standing") == "returning"
    assert set(state["intake"].get("completed", [])) == {"CS 135", "MATH 135"}
    plan = state["plan"]
    scheduled = [c for t in plan["terms"] for c in t.get("courses", [])]
    # Completed courses are not rescheduled.
    assert "CS 135" not in scheduled and "MATH 135" not in scheduled
    # Completed credits count toward the 40-course / 20-credit degree.
    assert plan["total_courses"] + 2 == 40
    assert plan["complete"]


def test_new_student_still_full_40() -> None:
    state = _run([
        "i am in computer science", "new first year",
        "domestic", "math co-op", "Fall 2026", "backend engineer",
    ])
    assert state["plan"]["total_courses"] == 40
    assert state["plan"]["complete"]
