"""Multi-term sequence planner.

Given an intake (program + sequence + start term + career) it plans every
*study* term of the sequence in order, threading completed courses forward so
prerequisites unlock, and steering each term toward the still-unmet degree
requirements. Work terms are passed through as co-op placeholders.

The single-term OR core (``scheduler.solve``) does the actual optimization for
each term; this module is the term-by-term loop and requirement bookkeeping.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from data.knowledge_base import score_courses
from data.prefilter import prefilter_candidates
from data.program_reqs import get_program_reqs
from data.sequences import Sequence, format_term, get_sequence, resolve_term
from data.uw_api import fetch_courses
from scheduler.solve import solve
from scheduler.types import Course, SolverConfig

# Default per-term load when the user hasn't specified one (4-5 half-credit courses).
_DEFAULT_MIN_UNITS = 2.0
_DEFAULT_MAX_UNITS = 2.5


def _remaining_reqs(reqs: dict[str, int], catalog: list[Course], completed: set[str]) -> dict[str, int]:
    completed_courses = [c for c in catalog if c.course_id in completed]
    remaining: dict[str, int] = {}
    for category, required in reqs.items():
        done = sum(1 for c in completed_courses if category in c.categories)
        rem = max(0, int(required) - done)
        if rem > 0:
            remaining[category] = rem
    return remaining


def _boost_needed(courses: list[Course], remaining: dict[str, int]) -> None:
    """Raise relevance of courses covering still-needed requirement categories.

    Ensures degree progress (foundational/required courses) is prioritized even
    when their raw career-relevance is low.
    """

    needed = {cat for cat, n in remaining.items() if n > 0}
    for c in courses:
        if needed & set(c.categories):
            c.career_relevance = max(c.career_relevance, 0.85)


def _term_config(base: dict[str, Any], min_easy: int) -> SolverConfig:
    """Per-term solver config: keep preferences, drop cumulative program reqs."""

    credit = base.get("credit_load") or {}
    data = dict(base)
    data["credit_load"] = {
        "min": float(credit.get("min", _DEFAULT_MIN_UNITS)),
        "max": float(credit.get("max", _DEFAULT_MAX_UNITS)),
    }
    data["program_reqs"] = {}              # requirements are cumulative, not per-term
    data["min_easy_courses"] = max(int(base.get("min_easy_courses", 0)), min_easy)
    return SolverConfig.from_dict(data)


def _solve_term(candidates: list[Course], cfg: SolverConfig):
    """Solve a term, relaxing softly if the strict config is infeasible."""

    res = solve(candidates, None, cfg)
    if res.feasible:
        return res, []
    notes: list[str] = []
    # Relax the easy-course floor first.
    if cfg.min_easy_courses > 0:
        res = solve(candidates, None, replace(cfg, min_easy_courses=0))
        if res.feasible:
            notes.append("couldn't fit an easy course this term")
            return res, notes
    # Then relax the credit floor to whatever fits.
    res = solve(candidates, None, replace(cfg, min_units=0.0, min_easy_courses=0))
    if res.feasible:
        notes.append("fewer courses than usual were available")
    return res, notes


def plan_sequence(
    intake: dict[str, Any],
    config: dict[str, Any] | None,
    completed: set[str] | None,
    career_goal: str,
) -> dict[str, Any]:
    """Produce a term-by-term plan across the whole study sequence."""

    seq: Sequence | None = get_sequence(intake.get("sequence"))
    start = intake.get("start_term") or {"season": "Fall", "year": 2026}
    base_cfg = dict(config or {})
    completed = set(completed or set())

    catalog = fetch_courses()
    degree_reqs = get_program_reqs(intake.get("reqs_key"))
    remaining = _remaining_reqs(degree_reqs, catalog, completed)
    min_easy = int(base_cfg.get("min_easy_courses", 0))

    terms_out: list[dict[str, Any]] = []
    if seq is None:
        return {"error": "unknown sequence", "terms": terms_out}

    study_done = 0
    for slot in seq.slots:
        cal = resolve_term(start, slot.year_offset, slot.season)
        if slot.kind == "work":
            terms_out.append({
                "label": slot.label, "kind": "work",
                "season": cal["season"], "year": cal["year"],
                "display": format_term(cal),
                "courses": [], "sections": [], "note": "Co-op work term",
            })
            continue

        # Study term.
        study_done += 1
        candidates = prefilter_candidates(catalog, completed=completed, term=None)
        if not candidates:
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": [], "sections": [],
                "note": "No further courses available in the catalog -- open electives.",
            })
            continue

        score_courses(candidates, career_goal)
        _boost_needed(candidates, remaining)
        cfg = _term_config(base_cfg, min_easy)
        res, notes = _solve_term(candidates, cfg)

        if res.feasible:
            completed |= set(res.selected_courses)
            chosen = [c for c in candidates if c.course_id in res.selected_courses]
            for cat in list(remaining.keys()):
                covered = sum(1 for c in chosen if cat in c.categories)
                remaining[cat] = max(0, remaining[cat] - covered)
                if remaining[cat] == 0:
                    del remaining[cat]
            sched = res.as_dict()
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": sched["courses"], "sections": sched["sections"],
                "total_units": sched["total_units"],
                "note": "; ".join(notes),
            })
        else:
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": [], "sections": [],
                "note": "Couldn't build a valid term here.",
            })

        # Stop early once degree requirements are met and no courses remain useful.
        if not remaining and study_done >= 1:
            # Continue filling remaining study terms only if catalog still has
            # career-relevant courses; otherwise stop to avoid empty electives.
            leftover = prefilter_candidates(catalog, completed=completed, term=None)
            if not leftover:
                break

    return {
        "program": intake.get("program"),
        "faculty": intake.get("faculty"),
        "sequence": seq.name,
        "start_term": format_term(start),
        "terms": terms_out,
        "requirements": degree_reqs,
        "remaining_requirements": remaining,
        "complete": not remaining,
    }
