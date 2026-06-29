"""Co-op sequence (Math) and stream (Engineering) coverage."""

from __future__ import annotations

from agent.planner import plan_sequence
from data.sequences import (
    SEQUENCES,
    default_eng_stream,
    describe_sequences,
    match_sequence,
    sequences_for_faculty,
)
from eval.checker import verify_plan

_MATH_COOP = ["math-coop", "math-coop-2", "math-coop-3", "math-coop-4"]


def test_four_math_coop_sequences_exist() -> None:
    keys = [s.key for s in sequences_for_faculty("Math")]
    assert keys == ["math-regular", *_MATH_COOP]


def test_every_math_sequence_has_eight_study_terms() -> None:
    for k in _MATH_COOP:
        labels = [s.label for s in SEQUENCES[k].slots if s.kind == "study"]
        assert labels == ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"]


def test_match_specific_math_sequence() -> None:
    assert match_sequence("math co-op", "Math") == "math-coop"           # default = Seq 1
    assert match_sequence("sequence 3", "Math") == "math-coop-3"
    assert match_sequence("seq 2", "Math") == "math-coop-2"
    assert match_sequence("co-op stream 4", "Math") == "math-coop-4"
    assert match_sequence("regular, no co-op", "Math") == "math-regular"


def test_engineering_streams() -> None:
    assert match_sequence("stream 4", "Engineering") == "eng-stream4"
    assert match_sequence("stream 8", "Engineering") == "eng-stream8"
    # Stream 4 starts co-op earlier than Stream 8.
    s4_first = next(i for i, s in enumerate(SEQUENCES["eng-stream4"].slots) if s.kind == "work")
    s8_first = next(i for i, s in enumerate(SEQUENCES["eng-stream8"].slots) if s.kind == "work")
    assert s4_first < s8_first


def test_program_stream_assignment() -> None:
    assert default_eng_stream("Software Engineering") == "eng-stream8"
    assert default_eng_stream("Mechatronics Engineering") is None  # assigned later / by choice


def test_all_math_sequences_produce_complete_plans() -> None:
    base = {
        "program": "Computer Science", "faculty": "Math", "reqs_key": "CS-Major",
        "residency": "domestic", "start_term": {"season": "Fall", "year": 2026},
        "career_goal": "exploring options",
    }
    for k in _MATH_COOP:
        plan = plan_sequence({**base, "sequence": k}, {}, set(), "exploring options")
        assert plan["complete"], k
        assert verify_plan(plan, completed=set())["all_ok"], k


def test_describe_sequences_lists_options() -> None:
    text = describe_sequences("Math")
    assert "Sequence 1" in text and "Sequence 4" in text
