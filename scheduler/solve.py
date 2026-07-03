"""Solve the scheduling model and, when infeasible, diagnose why.

Deterministic: this is an exact solver call, never an LLM. With a few dozen to
a few hundred candidate sections, CP-SAT returns in milliseconds.
"""

from __future__ import annotations

from dataclasses import replace

from ortools.sat.python import cp_model

from scheduler.conflicts import find_conflicts
from scheduler.model import BuiltModel, build_model
from scheduler.types import Course, ScheduleResult, Section, SolverConfig

_STATUS_NAMES = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


def _extract(built: BuiltModel, solver: cp_model.CpSolver) -> tuple[list[Section], list[str], float]:
    selected_sections: list[Section] = []
    selected_courses: list[str] = []
    for cid, var in built.y.items():
        if solver.Value(var) == 1:
            selected_courses.append(cid)
    for sid, var in built.x.items():
        if solver.Value(var) == 1:
            selected_sections.append(built.section_by_id[sid])  # type: ignore[arg-type]
    total_units = sum(built.courses_by_id[c].units for c in selected_courses)
    return selected_sections, selected_courses, total_units


def solve(
    courses: list[Course],
    conflicts: list[tuple[str, str]] | None,
    config: SolverConfig,
    *,
    max_time_s: float = 5.0,
) -> ScheduleResult:
    """Solve for the optimal schedule. Diagnose on infeasibility."""

    if conflicts is None:
        conflicts = find_conflicts(courses)

    built = build_model(courses, conflicts, config)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_s
    status = solver.Solve(built.model)
    status_name = _STATUS_NAMES.get(status, str(status))

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        sections, sel_courses, total_units = _extract(built, solver)
        sections.sort(key=lambda s: (s.course_id, s.section_code))
        sel_courses.sort()
        return ScheduleResult(
            feasible=True,
            status=status_name,
            selected_sections=sections,
            selected_courses=sel_courses,
            total_units=total_units,
            objective=solver.ObjectiveValue() / 1000.0,
        )

    return ScheduleResult(
        feasible=False,
        status=status_name,
        diagnosis=diagnose_infeasibility(courses, conflicts, config),
    )


def _feasible(courses: list[Course], conflicts: list[tuple[str, str]], config: SolverConfig) -> bool:
    built = build_model(courses, conflicts, config)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(built.model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def diagnose_infeasibility(
    courses: list[Course],
    conflicts: list[tuple[str, str]],
    config: SolverConfig,
) -> list[str]:
    """Locate the tightest hard constraints.

    Strategy: relax one user-imposed constraint group at a time and re-solve.
    Any relaxation that restores feasibility is reported as a culprit, giving
    the explanation layer concrete trade-offs to surface
    ("loosen X or drop Y").
    """

    findings: list[str] = []

    # Relax the credit-load floor.
    if config.min_units > 0:
        relaxed = replace(config, min_units=0.0)
        if _feasible(courses, conflicts, relaxed):
            findings.append(
                f"The minimum credit load ({config.min_units}) can't be reached "
                "given the other constraints -- lower it or allow more courses."
            )

    # Relax each program requirement independently.
    for category, required in config.program_reqs.items():
        relaxed_reqs = {k: v for k, v in config.program_reqs.items() if k != category}
        relaxed = replace(config, program_reqs=relaxed_reqs)
        if _feasible(courses, conflicts, relaxed):
            findings.append(
                f"Requirement '{category}' (needs {required}) can't be satisfied "
                "alongside your other choices -- relax it or free up time."
            )

    # Relax the "at least N easy courses" requirement.
    if config.min_easy_courses > 0:
        relaxed = replace(config, min_easy_courses=0)
        if _feasible(courses, conflicts, relaxed):
            findings.append(
                f"Requiring {config.min_easy_courses} easy course(s) can't be met "
                "with the other constraints -- drop it or widen the term."
            )

    # Relax must-include set.
    if config.must_include:
        relaxed = replace(config, must_include=[])
        if _feasible(courses, conflicts, relaxed):
            findings.append(
                "Your must-include courses clash with each other or with the "
                f"requirements: {', '.join(config.must_include)}."
            )

    # Relax credit ceiling (rarely the cause, but check).
    relaxed = replace(config, max_units=config.max_units + 1.0)
    if not findings and _feasible(courses, conflicts, relaxed):
        findings.append(
            f"The maximum credit load ({config.max_units}) is too low to cover "
            "everything required -- raise the ceiling."
        )

    if not findings:
        findings.append(
            "No single relaxation fixes it -- multiple constraints conflict at "
            "once. Try loosening time preferences and lowering the credit floor."
        )
    return findings
