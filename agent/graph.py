"""LangGraph assembly (Phase 2).

Graph (resume-visible agentic pipeline):

    gather_constraints → clarify | retrieve → plan_terms | build_model
    build_model → solve → diagnose | explain
    diagnose → explain
    plan_terms → explain
    clarify → explain

``run_turn`` mirrors the same edges without requiring LangGraph at import time.
"""

from __future__ import annotations

from typing import Any

from agent.intake import is_complete
from agent.understand import should_replan, wants_course_lookup
from agent.nodes import (
    build_model_node,
    clarify,
    diagnose,
    explain,
    gather_constraints,
    plan_terms,
    retrieve,
    solve_schedule,
)
from agent.state import PlannerState, last_user_message


def _merge(state: PlannerState, update: dict[str, Any]) -> PlannerState:
    merged: PlannerState = dict(state)  # type: ignore[assignment]
    merged.update(update)  # type: ignore[arg-type]
    return merged


def _route_after_gather(state: PlannerState) -> str:
    if wants_course_lookup(state) and not state.get("answering_onboarding"):
        return "explain"
    if state.get("needs_clarification"):
        return "clarify"
    return "retrieve"


def _route_after_retrieve(state: PlannerState) -> str:
    intake = state.get("intake") or {}
    if is_complete(intake, state.get("config")) and should_replan(state):
        return "plan_terms"
    if is_complete(intake, state.get("config")):
        return "explain"
    return "build_model"


def _route_after_solve(state: PlannerState) -> str:
    if state.get("infeasible"):
        return "diagnose"
    return "explain"


def _reset_state(state: PlannerState) -> PlannerState:
    """Clear the session back to a fresh onboarding (for "start over")."""

    return _merge(state, {
        "intake": {}, "config": None, "plan": None, "schedule": None,
        "profile": {"completed": []}, "career_goal": "",
        "needs_clarification": True, "replanned": False,
        "explanation": (
            "Okay, starting fresh! 🪿 Tell me about yourself — your program, whether "
            "you're a new first-year or returning (and any courses you've taken), and "
            "what you're aiming for."
        ),
        "clarification": "restart", "used_llm": False, "llm_understood": False,
        "llm_explained": False,
    })


def run_turn(state: PlannerState) -> PlannerState:
    """Run one planning turn functionally (no LangGraph dependency)."""

    from agent.plan_qa import is_reset

    if is_reset(state):
        return _reset_state(state)

    state = _merge(state, {"graph_trace": [], "replanned": False})
    state = _merge(state, gather_constraints(state))

    if wants_course_lookup(state) and not state.get("answering_onboarding"):
        state = _merge(state, explain(state))
        return state

    if state.get("needs_clarification"):
        state = _merge(state, clarify(state))
        state = _merge(state, explain(state))
        return state

    state = _merge(state, retrieve(state))

    intake = state.get("intake") or {}
    if is_complete(intake, state.get("config")) and should_replan(state):
        state = _merge(state, plan_terms(state))
    elif not state.get("plan"):
        # No plan yet and not ready for a full sequence solve — single-term preview.
        state = _merge(state, build_model_node(state))
        state = _merge(state, solve_schedule(state))
        if state.get("infeasible"):
            state = _merge(state, diagnose(state))
    # else: a plan exists and nothing changed — answer the question, don't re-solve.

    state = _merge(state, explain(state))
    return state


def build_graph() -> Any:
    """Construct and compile the LangGraph ``StateGraph``."""

    from langgraph.graph import END, START, StateGraph  # type: ignore

    graph = StateGraph(PlannerState)
    graph.add_node("gather_constraints", gather_constraints)
    graph.add_node("clarify", clarify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("build_model", build_model_node)
    graph.add_node("solve", solve_schedule)
    graph.add_node("diagnose", diagnose)
    graph.add_node("plan_terms", plan_terms)
    graph.add_node("explain", explain)

    graph.add_edge(START, "gather_constraints")
    graph.add_conditional_edges(
        "gather_constraints", _route_after_gather,
        {"clarify": "clarify", "retrieve": "retrieve", "explain": "explain"},
    )
    graph.add_conditional_edges(
        "retrieve", _route_after_retrieve,
        {"plan_terms": "plan_terms", "build_model": "build_model", "explain": "explain"},
    )
    graph.add_edge("build_model", "solve")
    graph.add_conditional_edges(
        "solve", _route_after_solve,
        {"diagnose": "diagnose", "explain": "explain"},
    )
    graph.add_edge("diagnose", "explain")
    graph.add_edge("clarify", "explain")
    graph.add_edge("plan_terms", "explain")
    graph.add_edge("explain", END)

    try:
        import os

        from langgraph.checkpoint.redis import RedisSaver  # type: ignore

        url = os.getenv("REDIS_URL")
        if url:
            return graph.compile(checkpointer=RedisSaver.from_conn_string(url))
    except Exception:
        pass
    return graph.compile()


def plan(state: PlannerState) -> PlannerState:
    """Single-turn entrypoint. Uses LangGraph if available, else ``run_turn``."""

    from agent.plan_qa import is_reset

    if is_reset(state):
        return _reset_state(state)

    try:
        app = build_graph()
    except Exception:
        return run_turn(state)
    try:
        return app.invoke(state)  # type: ignore[return-value]
    except Exception:
        return run_turn(state)
