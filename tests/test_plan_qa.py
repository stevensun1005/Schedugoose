"""Common post-plan conversations: help, facts, workload, reset, profile change.

These verify the router answers the question instead of re-dumping the plan.
"""

from __future__ import annotations

import copy

import pytest

from agent.graph import run_turn


@pytest.fixture(scope="module")
def planned():
    s = {"messages": [], "profile": {"completed": []}}
    for m in ["first year cs, backend engineer", "domestic", "math co-op", "Fall 2026"]:
        s["messages"].append({"role": "user", "content": m})
        s = run_turn(s)
        s["messages"].append({"role": "assistant", "content": s.get("explanation", "")})
    assert s.get("plan")
    return s


def _ask(state, msg):
    s = copy.deepcopy(state)
    s["messages"].append({"role": "user", "content": msg})
    s = run_turn(s)
    return s


def _reply(state, msg):
    return _ask(state, msg).get("explanation", "")


def test_backend_engineer_is_cs_not_engineering(planned):
    # "backend engineer" must not flip the program to Engineering.
    assert planned["intake"]["program"] == "Computer Science"


_DUMP = "Here's a term-by-term plan"


def test_greeting_does_not_dump_plan(planned):
    assert _DUMP not in _reply(planned, "hi")


def test_help_lists_capabilities(planned):
    r = _reply(planned, "what can you do?")
    assert "Revise" in r and "Look up a course" in r


def test_show_plan_renders_full_plan(planned):
    assert _DUMP in _reply(planned, "show me my plan")


def test_graduation_answer(planned):
    r = _reply(planned, "when do i graduate?")
    assert "graduate" in r.lower() and "4B" in r


def test_work_terms_answer(planned):
    r = _reply(planned, "when are my work terms?")
    assert "work term" in r.lower() and "WT1" in r


def test_prereq_question_routes_to_course_info(planned):
    r = _reply(planned, "what are the prerequisites for CS 341?")
    assert "CS 341" in r and "CS 240" in r  # its prereq


def test_workload_specific_term(planned):
    r = _reply(planned, "how heavy is 2A?")
    assert "2A" in r and _DUMP not in r


def test_offtopic_declines(planned):
    r = _reply(planned, "what's the weather today?")
    assert "course planner" in r.lower() and _DUMP not in r


def test_thanks_smalltalk(planned):
    assert "welcome" in _reply(planned, "thanks!").lower()


def test_reset_clears_plan(planned):
    s = _ask(planned, "start over")
    assert s.get("plan") is None
    assert not s.get("intake")
    assert "fresh" in s.get("explanation", "").lower()


def test_change_start_term_replans(planned):
    s = _ask(planned, "actually change my start term to winter 2027")
    assert s.get("replanned")
    one_a = next(t for t in s["plan"]["terms"] if t["label"] == "1A")
    assert one_a["display"] == "Winter 2027"


def test_switch_sequence_replans(planned):
    s = _ask(planned, "switch to sequence 2")
    assert s["intake"]["sequence"] == "math-coop-2"
    assert s.get("replanned")


def test_add_specialization_mid_conversation_replans(planned):
    # "I also want the business specialization" must update the plan, not no-op.
    s = _ask(planned, "i also want business specialization")
    assert s.get("replanned")
    assert "Business" in (s["plan"].get("degree_plan") or "")
    scheduled = {c for t in s["plan"]["terms"] for c in t.get("courses", [])}
    assert scheduled & {"ECON 101", "ENGL 119", "SPCOM 223", "ENGL 210"}


def test_question_does_not_accidentally_replan(planned):
    # A workload question must not silently rebuild the plan.
    s = _ask(planned, "which term is the hardest?")
    assert not s.get("replanned")
