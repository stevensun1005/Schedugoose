"""solve node: run OR-Tools CP-SAT (deterministic, never LLM)."""

from __future__ import annotations

from typing import Any

from agent.state import PlannerState
from agent.term_pipeline import append_trace, solve_with_relaxation
from scheduler.types import SolverConfig


def solve_schedule(state: PlannerState) -> dict[str, Any]:
    candidates = state.get("candidates") or []
    cfg = SolverConfig.from_dict(state.get("config") or {})
    res, notes = solve_with_relaxation(candidates, cfg)

    update: dict[str, Any] = {
        "last_solve_status": res.status,
        "infeasible": not res.feasible,
        "graph_trace": append_trace(state.get("graph_trace"), "solve", res.status),
    }
    if res.feasible:
        sched = res.as_dict()
        if notes:
            sched["relaxation_notes"] = notes
        update["schedule"] = sched
        update["diagnosis"] = []
    else:
        update["schedule"] = None
        update["diagnosis"] = list(res.diagnosis)
    return update
