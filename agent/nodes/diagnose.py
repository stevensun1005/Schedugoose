"""diagnose node: surface infeasibility culprits for the explanation layer."""

from __future__ import annotations

from typing import Any

from agent.state import PlannerState
from agent.term_pipeline import append_trace, diagnose_term
from scheduler.types import SolverConfig


def diagnose(state: PlannerState) -> dict[str, Any]:
    if not state.get("infeasible"):
        return {}

    candidates = state.get("candidates") or []
    conflicts = state.get("conflicts") or []
    cfg = SolverConfig.from_dict(state.get("config") or {})

    findings = list(state.get("diagnosis") or [])
    if not findings and candidates:
        findings = diagnose_term(candidates, conflicts, cfg)

    return {
        "diagnosis": findings,
        "graph_trace": append_trace(
            state.get("graph_trace"), "diagnose", f"{len(findings)} finding(s)",
        ),
    }
