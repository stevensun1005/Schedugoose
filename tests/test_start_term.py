"""Start-term handling: the plan must honor the season the student gave."""

from __future__ import annotations

from agent.planner import plan_sequence
from data.sequences import format_term, get_sequence, parse_start_term, resolve_term


def _first_terms(start_text: str, n: int = 4) -> list[str]:
    start = parse_start_term(start_text)
    seq = get_sequence("math-coop")
    return [format_term(resolve_term(start, s.year_offset, s.season)) for s in seq.slots[:n]]


def test_winter_start_is_honored() -> None:
    # The reported bug: "winter 2027" became "Fall 2027".
    assert _first_terms("winter 2027")[0] == "Winter 2027"


def test_fall_start_unchanged() -> None:
    # Default Fall start must still progress Fall → Winter(+1) → Spring(+1).
    assert _first_terms("fall 2026") == ["Fall 2026", "Winter 2027", "Spring 2027", "Fall 2027"]


def test_terms_are_calendar_consecutive() -> None:
    # Each study/work slot is the next calendar term, no gaps or year jumps.
    assert _first_terms("winter 2027") == ["Winter 2027", "Spring 2027", "Fall 2027", "Winter 2028"]
    assert _first_terms("spring 2027") == ["Spring 2027", "Fall 2027", "Winter 2028", "Spring 2028"]


def test_full_plan_starts_in_requested_season() -> None:
    intake = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "sequence": "math-coop",
        "start_term": {"season": "Winter", "year": 2027}, "career_goal": "exploring options",
    }
    plan = plan_sequence(intake, {}, set(), "exploring options")
    one_a = next(t for t in plan["terms"] if t["label"] == "1A")
    assert one_a["display"] == "Winter 2027"
    assert plan["complete"]
