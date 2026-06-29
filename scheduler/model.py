"""Integer-programming model construction (OR core).

Builds the CP-SAT model from candidate courses, precomputed conflicts and a
:class:`SolverConfig`. Pure construction only -- solving lives in ``solve.py``.

Variables
---------
* ``x[s] in {0,1}`` -- section ``s`` is selected.
* ``y[c] in {0,1}`` -- course ``c`` is in the schedule (linked to its sections).

CP-SAT is integer-only, so all float scores/weights are scaled to integers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from scheduler.types import Course, SolverConfig

# Fixed-point scale for turning [0,1] floats into solver-friendly integers.
SCALE: int = 1000


@dataclass
class BuiltModel:
    """A constructed model plus the handles needed to read a solution back."""

    model: cp_model.CpModel
    x: dict[str, cp_model.IntVar]                 # section id -> bool var
    y: dict[str, cp_model.IntVar]                 # course id  -> bool var
    courses_by_id: dict[str, Course]
    section_by_id: dict[str, object]              # section id -> Section
    # Named constraint groups, used by the infeasibility diagnosis.
    constraint_tags: dict[str, list] = field(default_factory=dict)


def _is_early(section, early_before: int) -> bool:
    return any(t.start < early_before for t in section.times)


def _on_friday(section) -> bool:
    return any("F" in t.days for t in section.times)


def course_score(course: Course, config: SolverConfig) -> int:
    """Scaled integer objective contribution for selecting ``course``."""

    w = config.weights
    raw = (
        w.career * course.career_relevance
        + w.easy * course.easiness
        + w.prof * course.prof_rating
    )
    return round(raw * SCALE)


def build_model(
    courses: list[Course],
    conflicts: list[tuple[str, str]],
    config: SolverConfig,
) -> BuiltModel:
    """Assemble the CP-SAT model. Returns variable handles for extraction."""

    m = cp_model.CpModel()
    courses_by_id = {c.course_id: c for c in courses}
    section_by_id = {s.id: s for c in courses for s in c.sections}

    x = {s.id: m.NewBoolVar(s.id) for c in courses for s in c.sections}
    y = {c.course_id: m.NewBoolVar(c.course_id.replace(" ", "_")) for c in courses}

    tags: dict[str, list] = {
        "linking": [],
        "conflicts": [],
        "credit": [],
        "program": [],
        "must_include": [],
        "must_avoid": [],
    }

    # (H1) Course-section linking: one section per required component.
    for c in courses:
        for comp in c.components():
            ct = m.Add(sum(x[s.id] for s in c.sections_of(comp)) == y[c.course_id])
            tags["linking"].append(ct)

    # (H2) No time conflicts.
    for s1, s2 in conflicts:
        if s1 in x and s2 in x:
            ct = m.Add(x[s1] + x[s2] <= 1)
            tags["conflicts"].append(ct)

    # (H3) Credit load (scaled by 10 to keep half-credit precision integral).
    load = sum(round(c.units * 10) * y[c.course_id] for c in courses)
    tags["credit"].append(m.Add(load >= round(config.min_units * 10)))
    tags["credit"].append(m.Add(load <= round(config.max_units * 10)))

    # (H4) Program requirement coverage. When a requirement has no candidate
    # courses, ``sum([]) == 0 >= required`` is added and renders the model
    # infeasible (correctly), rather than being silently dropped.
    for category, required in config.program_reqs.items():
        if required <= 0:
            continue
        members = [y[c.course_id] for c in courses if category in c.categories]
        tags["program"].append(m.Add(sum(members) >= required))

    # (H5b) Workload balancing: at least N "easy" courses.
    if config.min_easy_courses > 0:
        easy = [y[c.course_id] for c in courses if c.easiness >= config.easy_threshold]
        tags.setdefault("easy", [])
        tags["easy"].append(m.Add(sum(easy) >= config.min_easy_courses))

    # (H5) Must-include / must-avoid.
    for cid in config.must_include:
        if cid in y:
            tags["must_include"].append(m.Add(y[cid] == 1))
    for cid in config.must_avoid:
        if cid in y:
            tags["must_avoid"].append(m.Add(y[cid] == 0))

    # Objective: maximize weighted relevance, penalize early / Friday sections.
    w = config.weights
    obj_terms = [course_score(c, config) * y[c.course_id] for c in courses]
    for c in courses:
        for s in c.sections:
            penalty = 0
            if w.morning and _is_early(s, config.early_before):
                penalty += round(w.morning * SCALE)
            if (w.friday or config.avoid_friday) and _on_friday(s):
                penalty += round(max(w.friday, 0.1 if config.avoid_friday else 0) * SCALE)
            if penalty:
                obj_terms.append(-penalty * x[s.id])
    m.Maximize(sum(obj_terms))

    return BuiltModel(
        model=m,
        x=x,
        y=y,
        courses_by_id=courses_by_id,
        section_by_id=section_by_id,
        constraint_tags=tags,
    )
