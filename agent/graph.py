"""LangGraph assembly.

Flow: onboarding intake (gather) -> clarify (if info missing) -> multi-term
sequence plan -> explain -> iterate. Conditional edges handle the clarification
loop and revision turns.

``run_turn`` is a dependency-free functional implementation of the same graph
so the system runs without the optional LangGraph stack. ``build_graph`` builds
the real ``StateGraph`` when LangGraph is installed; both drive the *same* node
functions.
"""

from __future__ import annotations

from typing import Any

from agent.nodes import clarify, explain, gather_constraints, plan_terms
from agent.state import PlannerState


def _merge(state: PlannerState, update: dict[str, Any]) -> PlannerState:
    merged: PlannerState = dict(state)  # type: ignore[assignment]
    merged.update(update)  # type: ignore[arg-type]
    return merged


def run_turn(state: PlannerState) -> PlannerState:
    """Run one planning turn functionally (no LangGraph dependency)."""

    state = _merge(state, gather_constraints(state))

    # Conditional edge: still onboarding -> ask one question and wait.
    if state.get("needs_clarification"):
        state = _merge(state, clarify(state))
        state = _merge(state, explain(state))
        return state

    state = _merge(state, plan_terms(state))
    state = _merge(state, explain(state))
    return state


# --------------------------------------------------------------------------- #
# Real LangGraph build (optional)
# --------------------------------------------------------------------------- #
def _route_after_gather(state: PlannerState) -> str:
    return "clarify" if state.get("needs_clarification") else "plan_terms"


def build_graph() -> Any:
    """Construct and compile the LangGraph ``StateGraph``.

    Raises ``ImportError`` if LangGraph isn't installed -- callers fall back to
    :func:`run_turn`.
    """

    from langgraph.graph import END, START, StateGraph  # type: ignore

    graph = StateGraph(PlannerState)
    graph.add_node("gather_constraints", gather_constraints)
    graph.add_node("clarify", clarify)
    graph.add_node("plan_terms", plan_terms)
    graph.add_node("explain", explain)

    graph.add_edge(START, "gather_constraints")
    graph.add_conditional_edges(
        "gather_constraints", _route_after_gather,
        {"clarify": "clarify", "plan_terms": "plan_terms"},
    )
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

    try:
        app = build_graph()
    except Exception:
        return run_turn(state)
    try:
        return app.invoke(state)  # type: ignore[return-value]
    except Exception:
        return run_turn(state)
