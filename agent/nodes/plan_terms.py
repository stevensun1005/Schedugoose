"""plan_terms node: multi-term sequence planning via the OR pipeline."""

from __future__ import annotations

from typing import Any

from agent.planner import plan_sequence
from agent.state import PlannerState
from agent.term_pipeline import append_trace
from data.rag_store import retrieve_career_context


def plan_terms(state: PlannerState) -> dict[str, Any]:
    intake = state.get("intake", {}) or {}
    profile = state.get("profile", {}) or {}
    # Transcript can come from the UI profile or be captured in chat (intake).
    completed = set(profile.get("completed", []) or []) | set(intake.get("completed", []) or [])
    career = state.get("career_goal", "")

    grounded = set(state.get("grounded_codes") or [])
    hits_meta = state.get("rag_hits") or []
    if grounded:
        trace = append_trace(
            state.get("graph_trace"),
            "retrieve",
            f"RAG {hits_meta[0].get('source', 'cosine') if hits_meta else 'cosine'}",
        )
    else:
        hits, _, grounded_set = retrieve_career_context(career, top_k=2)
        grounded = grounded_set
        trace = append_trace(
            state.get("graph_trace"),
            "retrieve",
            f"RAG {hits[0].source if hits else 'cosine'}",
        )

    plan = plan_sequence(
        intake=intake,
        config=state.get("config"),
        completed=completed,
        career_goal=career,
        grounded_codes=grounded,
        graph_trace=trace,
    )
    return {
        "plan": plan,
        "schedule": None,
        "infeasible": not plan.get("complete", False) and any(
            not t.get("courses") for t in plan.get("terms", [])
            if t.get("kind") == "study"
        ),
        "graph_trace": plan.get("graph_trace", trace),
    }