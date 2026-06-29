"""Multi-term sequence planner.

Plans every study term until graduation (20.0 academic credits / 40 courses).
Each study term runs the explicit OR pipeline: retrieve → build_model → solve
(→ diagnose on failure). The LLM never schedules.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from data.course_utils import counts_toward_degree, term_year
from data.degree_plans import (
    DOMESTIC_LANGUAGE_CATEGORY,
    INTL_ENGLISH_CATEGORY,
    language_category,
    plan_from_intake,
    resolve_requirements,
)
from data.program_reqs import MIN_DEGREE_UNITS
from data.sequences import Sequence, format_term, get_sequence, resolve_term
from data.uw_api import fetch_courses
from agent.term_pipeline import (
    append_trace,
    build_term_model,
    diagnose_term,
    retrieve_for_term,
    solve_with_relaxation,
    term_config,
)
from scheduler.types import Course

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
    needed = {cat for cat, n in remaining.items() if n > 0}
    for c in courses:
        overlap = needed & set(c.categories)
        if overlap:
            c.career_relevance = max(c.career_relevance, 1.0 if "Core" in "".join(overlap) else 0.9)


def _term_must_include(
    slot_label: str, base_cfg: dict[str, Any], candidates: list[Course],
) -> list[str]:
    term_reqs = base_cfg.get("term_requirements") or {}
    reqs = list(term_reqs.get(slot_label, []))
    must: list[str] = []
    for req in reqs:
        if req in (DOMESTIC_LANGUAGE_CATEGORY, INTL_ENGLISH_CATEGORY, "Language"):
            cat = req if req != "Language" else DOMESTIC_LANGUAGE_CATEGORY
            pool = sorted(
                c.course_id for c in candidates
                if cat in c.categories or (cat == DOMESTIC_LANGUAGE_CATEGORY and "Language" in c.categories)
            )
            if pool:
                must.append(pool[0])
        elif " " in req or req.isupper():
            must.append(req)
    return must


def _required_core_this_term(
    candidates: list[Course], remaining: dict[str, int], slot_label: str,
) -> list[str]:
    year = term_year(slot_label)
    if year > 2:
        return []
    picks: list[str] = []
    per_cat = 2 if year == 1 else 1
    for cat in ("CS-Core", "Math-Core"):
        if remaining.get(cat, 0) <= 0:
            continue
        n = 0
        for c in sorted(candidates, key=lambda x: x.course_id):
            if cat in c.categories and c.course_id not in picks:
                picks.append(c.course_id)
                n += 1
                if n >= per_cat:
                    break
    return picks


def _min_easy_this_term(min_easy: int, remaining: dict[str, int], slot_label: str) -> int:
    core_left = sum(remaining.get(k, 0) for k in ("CS-Core", "Math-Core", "STAT-Core", "Comm"))
    if core_left > 0 and term_year(slot_label) <= 2:
        return 0
    return min_easy


def _boost_elective_picks(courses: list[Course], picks: set[str]) -> None:
    for c in courses:
        if c.course_id in picks:
            c.easiness = max(c.easiness, 0.95)
            c.career_relevance = max(c.career_relevance, 0.5)


def _pd_for_work_term(label: str, catalog: list[Course]) -> str | None:
    if not label.startswith("WT"):
        return None
    try:
        n = int(label[2:])
    except ValueError:
        return None
    code = f"PD {n}"
    if any(c.course_id == code for c in catalog):
        return code
    return None


def _units_so_far(catalog: list[Course], completed: set[str]) -> float:
    by_id = {c.course_id: c for c in catalog}
    return sum(by_id[cid].units for cid in completed if cid in by_id and counts_toward_degree(by_id[cid]))


def _apply_residency_language(intake: dict[str, Any], base_cfg: dict[str, Any]) -> None:
    residency = intake.get("residency")
    if not residency:
        return
    lang_cat = language_category(residency)  # type: ignore[arg-type]
    tr = base_cfg.setdefault("term_requirements", {})
    tr["1A"] = [
        x for x in tr.get("1A", [])
        if x not in (DOMESTIC_LANGUAGE_CATEGORY, INTL_ENGLISH_CATEGORY, "Language")
    ]
    if lang_cat not in tr["1A"]:
        tr["1A"].append(lang_cat)


def plan_sequence(
    intake: dict[str, Any],
    config: dict[str, Any] | None,
    completed: set[str] | None,
    career_goal: str,
    *,
    grounded_codes: set[str] | None = None,
    graph_trace: list[str] | None = None,
) -> dict[str, Any]:
    seq: Sequence | None = get_sequence(intake.get("sequence"))
    start = intake.get("start_term") or {"season": "Fall", "year": 2026}
    base_cfg = dict(config or {})
    completed = set(completed or set())
    elective_picks = set(intake.get("elective_picks") or [])
    pending_electives = set(elective_picks)
    trace = list(graph_trace or [])

    catalog = fetch_courses(start_term=start)
    degree_plan = plan_from_intake(intake)
    degree_reqs = resolve_requirements(degree_plan)
    remaining = _remaining_reqs(degree_reqs, catalog, completed)
    min_easy = int(base_cfg.get("min_easy_courses", 0))
    _apply_residency_language(intake, base_cfg)

    terms_out: list[dict[str, Any]] = []
    if seq is None:
        return {"error": "unknown sequence", "terms": terms_out, "graph_trace": trace}

    for slot in seq.slots:
        cal = resolve_term(start, slot.year_offset, slot.season)

        if slot.kind == "work":
            pd_code = _pd_for_work_term(slot.label, catalog)
            terms_out.append({
                "label": slot.label, "kind": "work",
                "season": cal["season"], "year": cal["year"],
                "display": format_term(cal),
                "courses": [pd_code] if pd_code else [],
                "sections": [],
                "note": "Co-op work term" + (f" + {pd_code} (PD, 0 degree credit)" if pd_code else ""),
            })
            continue

        candidates = retrieve_for_term(
            catalog,
            completed=completed,
            slot_label=slot.label,
            career_goal=career_goal,
            grounded_codes=grounded_codes,
            program=intake.get("program"),
            faculty=intake.get("faculty"),
        )
        term_avoid = base_cfg.get("term_avoid") or {}
        avoid_ids = set(term_avoid.get(slot.label, []))
        if avoid_ids:
            candidates = [c for c in candidates if c.course_id not in avoid_ids]
        trace = append_trace(trace, f"retrieve/{slot.label}", f"{len(candidates)} candidates")

        if not candidates:
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": [], "sections": [],
                "note": "No eligible courses left -- add electives or adjust picks.",
            })
            continue

        units_done = _units_so_far(catalog, completed)
        remaining_credits = round(MIN_DEGREE_UNITS - units_done, 2)

        # Returning students may already satisfy the degree before the sequence
        # ends — stop adding courses instead of overshooting 20 credits / 40 courses.
        if remaining_credits <= 0 and not remaining:
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": [], "sections": [],
                "note": "Degree requirements already met — no courses needed this term.",
            })
            continue

        _boost_needed(candidates, remaining)
        _boost_elective_picks(candidates, pending_electives)

        easy_floor = _min_easy_this_term(min_easy, remaining, slot.label)

        cfg_data = dict(base_cfg)
        credit = dict(cfg_data.get("credit_load") or {})
        if units_done < MIN_DEGREE_UNITS:
            # Cap the final term so completed credits aren't double-counted past 20.
            cap = min(2.5, remaining_credits)
            credit["min"] = cap
            credit["max"] = cap
        cfg_data["credit_load"] = credit
        cfg_data["weights"] = dict(cfg_data.get("weights") or {})
        if sum(remaining.get(k, 0) for k in ("CS-Core", "Math-Core")) > 0:
            cfg_data["weights"]["career"] = max(float(cfg_data["weights"].get("career", 0.5)), 0.7)
            cfg_data["weights"]["easy"] = min(float(cfg_data["weights"].get("easy", 0.3)), 0.2)

        must_inc = _required_core_this_term(candidates, remaining, slot.label)
        term_pins = _term_must_include(slot.label, cfg_data, candidates)
        user_pins = [
            c for c in term_pins
            if " " in c and c.split()[0].isalpha()
        ]
        must_inc.extend(term_pins)
        must_inc = list(dict.fromkeys(must_inc))
        eligible_picks = [
            c.course_id for c in candidates
            if c.course_id in pending_electives and c.course_id not in avoid_ids
        ]
        if eligible_picks and easy_floor > 0 and len(must_inc) < 4:
            must_inc.append(eligible_picks[0])

        cfg = term_config(cfg_data, easy_floor, must_include=must_inc)
        if avoid_ids:
            cfg = replace(
                cfg,
                must_avoid=list(dict.fromkeys(list(cfg.must_avoid) + list(avoid_ids))),
            )
        conflicts, n_pairs = build_term_model(candidates, cfg)
        trace = append_trace(trace, f"build_model/{slot.label}", f"{n_pairs} pairs")

        res, notes = solve_with_relaxation(candidates, cfg, hard_include=user_pins)
        trace = append_trace(trace, f"solve/{slot.label}", res.status)

        if not res.feasible:
            findings = diagnose_term(candidates, conflicts, cfg)
            trace = append_trace(trace, f"diagnose/{slot.label}", f"{len(findings)} findings")

        if res.feasible:
            completed |= set(res.selected_courses)
            for cid in res.selected_courses:
                pending_electives.discard(cid)
            chosen = [c for c in candidates if c.course_id in res.selected_courses]
            for cat in list(remaining.keys()):
                covered = sum(1 for c in chosen if cat in c.categories)
                remaining[cat] = max(0, remaining[cat] - covered)
                if remaining[cat] == 0:
                    del remaining[cat]
            sched = res.as_dict()
            units = _units_so_far(catalog, completed)
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": sched["courses"], "sections": sched["sections"],
                "total_units": sched["total_units"],
                "cumulative_units": round(units, 2),
                "note": "; ".join(n for n in notes if n),
            })
        else:
            terms_out.append({
                "label": slot.label, "kind": "study",
                "season": cal["season"], "year": cal["year"], "display": format_term(cal),
                "courses": [], "sections": [],
                "note": "Couldn't build a valid term here.",
            })

    total_units = _units_so_far(catalog, completed)
    total_courses = sum(
        len(t["courses"]) for t in terms_out
        if t["kind"] == "study" and t.get("courses")
    )
    degree_ok = total_units >= MIN_DEGREE_UNITS and not remaining

    scheduled_ids = {
        c for t in terms_out if t["kind"] == "study" for c in t.get("courses", [])
    }
    scheduled_picks = [c for c in elective_picks if c in scheduled_ids]
    unscheduled_picks = sorted(pending_electives)

    return {
        "program": intake.get("program"),
        "faculty": intake.get("faculty"),
        "residency": intake.get("residency"),
        "degree_plan": degree_plan.display(),
        "sequence": seq.name,
        "start_term": format_term(start),
        "terms": terms_out,
        "requirements": degree_reqs,
        "remaining_requirements": remaining,
        "total_units": round(total_units, 2),
        "total_courses": total_courses,
        "graduation_target_units": MIN_DEGREE_UNITS,
        "complete": degree_ok,
        "elective_picks": sorted(elective_picks),
        "scheduled_picks": sorted(scheduled_picks),
        "unscheduled_picks": unscheduled_picks,
        "graph_trace": trace,
    }
