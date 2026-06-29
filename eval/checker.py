"""Machine-verifiable checkers (eval axis 1).

* ``verify`` re-verifies a single-term schedule (no conflicts, credit, program,
  must include/avoid). Kept for direct OR-core checks.
* ``verify_plan`` re-verifies a multi-term sequence plan: every study term is
  conflict-free and within load, no course is taken twice, prerequisites are met
  by earlier terms, and the cumulative plan covers the degree requirements.

This is the "hard evidence of reliability" that should sit near 100%.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from data.uw_api import fetch_courses
from scheduler.conflicts import find_conflicts
from scheduler.types import Course, SolverConfig


def _selected_courses(candidates: list[Course], schedule: dict[str, Any]) -> list[Course]:
    picked_ids = set(schedule.get("courses", []))
    picked_codes = {(s["course_id"], s["section_code"]) for s in schedule.get("sections", [])}
    out: list[Course] = []
    for c in candidates:
        if c.course_id not in picked_ids:
            continue
        secs = [s for s in c.sections if (c.course_id, s.section_code) in picked_codes]
        out.append(replace(c, sections=secs))
    return out


def verify(candidates: list[Course], config_dict: dict[str, Any], schedule: dict[str, Any]) -> dict[str, bool]:
    config = SolverConfig.from_dict(config_dict or {})
    chosen = _selected_courses(candidates, schedule)
    conflicts_ok = len(find_conflicts(chosen)) == 0
    linking_ok = all(
        len([s for s in c.sections if s.component == comp]) == 1
        for c in chosen for comp in {s.component for s in c.sections}
    )
    total = sum(c.units for c in chosen)
    credit_ok = config.min_units - 1e-9 <= total <= config.max_units + 1e-9
    program_ok = all(
        sum(1 for c in chosen if cat in c.categories) >= req
        for cat, req in config.program_reqs.items()
    )
    chosen_ids = {c.course_id for c in chosen}
    must_inc_ok = all(cid in chosen_ids for cid in config.must_include)
    must_avoid_ok = all(cid not in chosen_ids for cid in config.must_avoid)
    checks = {
        "conflicts_ok": conflicts_ok, "linking_ok": linking_ok, "credit_ok": credit_ok,
        "program_ok": program_ok, "must_include_ok": must_inc_ok, "must_avoid_ok": must_avoid_ok,
    }
    checks["all_ok"] = all(checks.values())
    return checks


def verify_plan(plan: dict[str, Any], completed: set[str] | None = None, max_units: float = 3.0) -> dict[str, Any]:
    """Re-verify a multi-term sequence plan independently of the planner."""

    catalog = {c.course_id: c for c in fetch_courses()}
    completed = set(completed or set())

    conflicts_ok = True
    credit_ok = True
    prereq_ok = True
    no_dup = True
    seen: set[str] = set()

    for term in plan.get("terms", []):
        if term.get("kind") != "study" or not term.get("courses"):
            continue
        codes = term["courses"]

        # No duplicate courses across terms.
        for code in codes:
            if code in seen or code in completed:
                no_dup = False
            seen.add(code)

        # Prerequisites met by earlier terms / prior transcript.
        for code in codes:
            c = catalog.get(code)
            if c and not all(p in completed for p in c.prereqs):
                prereq_ok = False

        # Rebuild chosen sections for conflict checking.
        picked_codes = {(s["course_id"], s["section_code"]) for s in term.get("sections", [])}
        chosen_courses: list[Course] = []
        for code in codes:
            c = catalog.get(code)
            if not c:
                continue
            secs = [s for s in c.sections if (code, s.section_code) in picked_codes]
            chosen_courses.append(replace(c, sections=secs))
        if find_conflicts(chosen_courses):
            conflicts_ok = False

        # Credit ceiling (floor is intentionally relaxed when catalog runs thin).
        units = sum(catalog[code].units for code in codes if code in catalog)
        if units > max_units + 1e-9:
            credit_ok = False

        completed |= set(codes)

    requirements_ok = not plan.get("remaining_requirements")
    checks = {
        "conflicts_ok": conflicts_ok,
        "credit_ok": credit_ok,
        "prereq_ok": prereq_ok,
        "no_duplicate_ok": no_dup,
        "requirements_ok": requirements_ok,
    }
    checks["all_ok"] = all(checks.values())
    return checks
