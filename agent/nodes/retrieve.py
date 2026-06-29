"""retrieve node: UW API + RAG grounding → scored candidate courses."""

from __future__ import annotations

from typing import Any

from agent.state import PlannerState
from agent.term_pipeline import append_trace, retrieve_for_term
from data.rag_store import retrieve_career_context
from data.uw_api import fetch_courses


def retrieve(state: PlannerState) -> dict[str, Any]:
    career = state.get("career_goal", "") or ""
    hits, categories, grounded = retrieve_career_context(career, top_k=2)

    config = dict(state.get("config") or {})
    merged_cats = list(config.get("target_categories") or [])
    for cat in categories:
        if cat not in merged_cats:
            merged_cats.append(cat)
    config["target_categories"] = merged_cats

    intake = state.get("intake") or {}
    catalog = fetch_courses(start_term=intake.get("start_term"))
    profile = state.get("profile") or {}
    completed = set(profile.get("completed") or [])
    slot = state.get("current_term") or "1A"

    candidates = retrieve_for_term(
        catalog,
        completed=completed,
        slot_label=slot,
        career_goal=career,
        grounded_codes=grounded,
        program=intake.get("program"),
        faculty=intake.get("faculty"),
    )

    rag_hits = [
        {
            "career": h.career,
            "score": h.score,
            "courses": list(h.courses),
            "categories": list(h.target_categories),
            "source": h.source,
        }
        for h in hits
    ]

    return {
        "catalog": catalog,
        "candidates": candidates,
        "config": config,
        "rag_hits": rag_hits,
        "grounded_codes": sorted(grounded),
        "graph_trace": append_trace(
            state.get("graph_trace"),
            "retrieve",
            f"{len(candidates)} candidates, RAG={hits[0].source if hits else 'none'}",
        ),
    }
