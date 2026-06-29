"""Per-term OR pipeline: retrieve → build_model → solve → diagnose.

Shared by LangGraph nodes and the multi-term sequence planner. The LLM never
enters this module.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from data.knowledge_base import score_courses
from data.prefilter import prefilter_candidates
from scheduler.conflicts import find_conflicts
from scheduler.model import build_model
from scheduler.solve import diagnose_infeasibility, solve
from scheduler.types import Course, ScheduleResult, SolverConfig

_DEFAULT_MIN_UNITS = 2.0
_DEFAULT_MAX_UNITS = 2.5


def append_trace(trace: list[str] | None, node: str, detail: str = "") -> list[str]:
    out = list(trace or [])
    out.append(f"{node}{f': {detail}' if detail else ''}")
    return out


def retrieve_for_term(
    catalog: list[Course],
    *,
    completed: set[str],
    slot_label: str,
    career_goal: str,
    grounded_codes: set[str] | None = None,
    program: str | None = None,
    faculty: str | None = None,
) -> list[Course]:
    """Pre-filter + RAG relevance scoring for one study term."""

    candidates = prefilter_candidates(
        catalog, completed=completed, slot_label=slot_label, study_term=True,
        program=program, faculty=faculty,
    )
    if not candidates:
        return []
    # Deep-copy so in-place scoring does not mutate the catalog.
    candidates = copy.deepcopy(candidates)
    score_courses(candidates, career_goal)
    if grounded_codes:
        for c in candidates:
            if c.course_id in grounded_codes:
                c.career_relevance = max(c.career_relevance, 1.0)
    return candidates


def build_term_model(candidates: list[Course], cfg: SolverConfig) -> tuple[list[tuple[str, str]], int]:
    """Precompute conflicts and validate the CP-SAT model builds."""

    conflicts = find_conflicts(candidates)
    build_model(candidates, conflicts, cfg)
    return conflicts, len(conflicts)


def solve_with_relaxation(
    candidates: list[Course],
    cfg: SolverConfig,
    *,
    hard_include: list[str] | None = None,
) -> tuple[ScheduleResult, list[str]]:
    """Solve one term; relax soft constraints on failure (user-pinned courses stay)."""

    hard_include = list(hard_include or [])
    res = solve(candidates, None, cfg)
    if res.feasible:
        return res, []
    notes: list[str] = []
    soft = [c for c in cfg.must_include if c not in hard_include]
    if soft:
        res = solve(candidates, None, replace(cfg, must_include=hard_include))
        if res.feasible:
            notes.append("couldn't fit all requested electives this term")
            return res, notes
    if cfg.min_easy_courses > 0:
        res = solve(
            candidates, None,
            replace(cfg, must_include=hard_include, min_easy_courses=0),
        )
        if res.feasible:
            notes.append("couldn't fit an easy course this term")
            return res, notes
    res = solve(
        candidates, None,
        replace(cfg, must_include=hard_include, min_units=0.0, min_easy_courses=0),
    )
    if res.feasible:
        notes.append("lighter load than target")
    return res, notes


def diagnose_term(
    candidates: list[Course],
    conflicts: list[tuple[str, str]],
    cfg: SolverConfig,
) -> list[str]:
    return diagnose_infeasibility(candidates, conflicts, cfg)


def term_config(
    base: dict[str, Any],
    min_easy: int,
    *,
    must_include: list[str] | None = None,
) -> SolverConfig:
    credit = base.get("credit_load") or {}
    data = dict(base)
    data["credit_load"] = {
        "min": float(credit.get("min", _DEFAULT_MIN_UNITS)),
        "max": float(credit.get("max", _DEFAULT_MAX_UNITS)),
    }
    data["program_reqs"] = {}
    data["min_easy_courses"] = min_easy
    if must_include:
        data["must_include"] = list(set((base.get("must_include") or []) + must_include))
    return SolverConfig.from_dict(data)
