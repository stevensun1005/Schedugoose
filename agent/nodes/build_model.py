"""build_model node: precompute conflicts and construct the CP-SAT model."""

from __future__ import annotations

from typing import Any

from agent.state import PlannerState
from agent.term_pipeline import append_trace, build_term_model
from scheduler.types import SolverConfig


def build_model_node(state: PlannerState) -> dict[str, Any]:
    candidates = state.get("candidates") or []
    cfg = SolverConfig.from_dict(state.get("config") or {})
    conflicts, n_pairs = build_term_model(candidates, cfg)
    return {
        "conflicts": conflicts,
        "model_ready": True,
        "graph_trace": append_trace(state.get("graph_trace"), "build_model", f"{n_pairs} conflict pairs"),
    }
