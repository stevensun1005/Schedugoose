"""explain node: plan + trade-offs -> natural language.

LLM path when available; otherwise a faithful template that narrates only what
is actually in the plan (no invention).
"""

from __future__ import annotations

import json
from typing import Any

from agent.advisory import advisory_reply, compact_plan_summary
from agent.converse import conversational_reply
from agent.course_qa import (
    answer_course_question,
    gather_course_facts,
)
from agent.llm import complete_text
from agent.requirements_qa import format_requirements_answer
from agent.understand import (
    course_codes_for_lookup,
    wants_advisory_reply,
    wants_course_lookup,
    wants_plan_revision,
    wants_requirements_qa,
)
from agent.state import PlannerState, last_user_message

_SYSTEM = """You are Schedugoose, a UW course-planning assistant. The user may ask \
what courses are required for a specialization — answer that directly first, then \
briefly describe how the term-by-term plan helps. Reference only courses present \
in the plan data. Be concise and friendly."""

_REVISION_SYSTEM = """You are Schedugoose, a UW course-planning assistant.
The user just asked to CHANGE their plan (swap/drop/add courses in specific terms).
1. Acknowledge what they asked for FIRST (e.g. removed ENGL from 2A, added CS 246).
2. Say whether the updated plan reflects that (use the revision notes and plan JSON).
3. Keep it short (2-4 sentences). Do not repeat the whole schedule — the UI shows it."""


def _template_plan(intake: dict[str, Any], config: dict[str, Any], plan: dict[str, Any]) -> str:
    lines: list[str] = []
    prog = plan.get("program") or intake.get("program") or "your program"
    residency = plan.get("residency") or intake.get("residency")
    res_note = ""
    if residency == "international":
        res_note = " (international — English proficiency course in 1A)"
    elif residency == "domestic":
        res_note = " (domestic — second-language course in 1A)"
    degree = plan.get("degree_plan") or ""
    degree_line = f" Degree: {degree}." if degree else ""
    lines.append(
        f"Here's a term-by-term plan for {prog} (CS program){res_note} on the {plan.get('sequence')} "
        f"sequence, starting {plan.get('start_term')}.{degree_line}"
    )
    for t in plan.get("terms", []):
        if t["kind"] == "work":
            pd = ", ".join(c for c in t.get("courses", []) if c.startswith("PD"))
            extra = f" + {pd}" if pd else ""
            lines.append(f"  - {t['label']} ({t['display']}): co-op work term{extra}")
        elif t.get("courses"):
            note = f" -- {t['note']}" if t.get("note") else ""
            cum = f" [{t.get('cumulative_units', '?')} cr total]" if t.get("cumulative_units") else ""
            lines.append(f"  - {t['label']} ({t['display']}): {', '.join(t['courses'])}{cum}{note}")
        else:
            lines.append(f"  - {t['label']} ({t['display']}): {t.get('note', 'open electives')}")

    scheduled_picks = plan.get("scheduled_picks") or []
    unscheduled_picks = plan.get("unscheduled_picks") or []
    if scheduled_picks:
        lines.append(f"Your chosen electives in the plan: {', '.join(scheduled_picks)}.")
    if unscheduled_picks:
        lines.append(
            f"Couldn't fit your picks {', '.join(unscheduled_picks)} — their prerequisites "
            "aren't met within this plan (or no open slot). Tell me to swap something out for them."
        )
    total_u = plan.get("total_units")
    target = plan.get("graduation_target_units", 20.0)
    if total_u is not None:
        lines.append(f"Plan total: {plan.get('total_courses', '?')} courses, {total_u} / {target} academic credits.")
    if plan.get("complete"):
        lines.append("This meets the 20-credit / 40-course graduation target and core requirements.")
    else:
        rem = plan.get("remaining_requirements") or {}
        if rem:
            need = ", ".join(f"{k} (+{v})" for k, v in rem.items())
            lines.append(f"Still to cover later: {need}.")
    trace = plan.get("graph_trace") or []
    if trace:
        lines.append(f"Agent pipeline ({len(trace)} steps): {' → '.join(trace[:6])}{'…' if len(trace) > 6 else ''}.")
    lines.append("Tell me to make a term lighter, avoid mornings, swap a course, or change your sequence and I'll re-plan.")
    return "\n".join(lines)


def _template_infeasible(state: PlannerState) -> str:
    lines = ["I couldn't build a feasible schedule for this term."]
    for d in state.get("diagnosis") or []:
        lines.append(f"  - {d}")
    lines.append("Try loosening credit load, dropping a must-include, or easing time preferences.")
    return "\n".join(lines)


from agent.revision import format_turn_revision_note


def explain(state: PlannerState) -> dict[str, Any]:
    intake = state.get("intake") or {}
    config = state.get("config") or {}
    plan = state.get("plan")
    user_msg = last_user_message(state)

    if wants_course_lookup(state):
        codes = course_codes_for_lookup(state)
        if not codes:
            return {"explanation": "Which course are you asking about? Give me a code like SOC 101."}
        facts = gather_course_facts(
            codes[0],
            intake=intake,
            catalog=state.get("catalog"),
            plan=plan,
        )
        answer, used_llm = answer_course_question(user_msg, facts)
        return {"explanation": answer, "used_llm": used_llm, "llm_explained": used_llm}

    # Help works in any state; plan facts (graduation, work terms, summary,
    # smalltalk, off-topic) once a plan exists — deterministic facts, but phrased
    # by the LLM so every turn runs through it (facts stay exact).
    from agent.llm import grounded_reply
    from agent.plan_qa import help_text, is_help_request, plan_qa_reply, wants_plan_summary

    def _grounded(text: str) -> dict[str, Any]:
        reply, used = grounded_reply(user_msg, text)
        return {"explanation": reply, "used_llm": used or bool(state.get("llm_understood")), "llm_explained": used}

    if is_help_request(state):
        return _grounded(help_text())
    if plan:
        if wants_plan_summary(state):
            return {"explanation": _template_plan(intake, config, plan),
                    "used_llm": bool(state.get("llm_understood")), "llm_explained": False}
        pq = plan_qa_reply(state)
        if pq is not None:
            return _grounded(pq)

    req_block = ""
    if plan and wants_requirements_qa(state):
        req_answer = format_requirements_answer(user_msg, intake, plan)
        # A pure requirements question → return the cited/RAG answer verbatim.
        # Never fall through to the general plan-explanation LLM, which would
        # append an ungrounded narrative (and invent courses).
        if not wants_plan_revision(state):
            return {"explanation": req_answer,
                    "used_llm": bool(state.get("llm_understood")), "llm_explained": False}
        req_block = req_answer + "\n\n---\n\n"

    if plan and wants_advisory_reply(state):
        delta = state.get("turn_revision") or {}
        adv_delta = {
            "term_avoid": delta.get("term_avoid") or {},
            "must_avoid": delta.get("must_avoid") or [],
            "term_requirements": {},
        }
        pin_note = format_turn_revision_note(adv_delta, plan)
        req_prefix = (pin_note + req_block) if pin_note else req_block
        reply, explained = advisory_reply(state)
        return {
            "explanation": req_prefix + reply,
            "used_llm": explained or bool(state.get("llm_understood")),
            "llm_explained": explained,
        }

    pin_note = format_turn_revision_note(state.get("turn_revision") or {}, plan) if plan else ""

    if not plan:
        if state.get("infeasible") and state.get("diagnosis"):
            return {"explanation": _template_infeasible(state)}
        if state.get("needs_clarification"):
            reply, used_llm = conversational_reply(state)
            explained = used_llm
            return {
                "explanation": reply,
                "clarification": reply,
                "used_llm": explained or bool(state.get("llm_understood")),
                "llm_explained": explained,
            }
        return {"explanation": "Tell me a bit more to get started."}

    rag = state.get("rag_hits") or []
    rag_note = ""
    if rag:
        rag_note = f"\nRAG grounding: {rag[0].get('career')} ({rag[0].get('source')}, score={rag[0].get('score')})."

    llm_text = complete_text(
        _REVISION_SYSTEM if wants_plan_revision(state) else _SYSTEM,
        f"User message:\n{user_msg}\n\n"
        f"Revision notes:\n{pin_note or '(none)'}\n\n"
        f"Career goal: {intake.get('career_goal')}\n"
        f"Plan summary:\n{compact_plan_summary(plan)}\n"
        f"Preferences (term pins/avoid): {json.dumps({k: config.get(k) for k in ('term_requirements', 'term_avoid') if config.get(k)}, default=str)}\n"
        f"{rag_note}",
    )
    if llm_text:
        return {
            "explanation": pin_note + req_block + llm_text,
            "used_llm": True,
            "llm_explained": True,
        }
    if wants_plan_revision(state):
        reply, explained = advisory_reply(state)
        return {
            "explanation": pin_note + req_block + reply,
            "used_llm": explained or bool(state.get("llm_understood")),
            "llm_explained": explained,
        }
    # Plan was just (re)built this turn → show the full term-by-term plan.
    if state.get("replanned"):
        return {
            "explanation": pin_note + req_block + _template_plan(intake, config, plan),
            "used_llm": bool(state.get("llm_understood")),
            "llm_explained": False,
        }
    # A plan already exists and this turn didn't change it — answer briefly
    # instead of re-dumping the whole schedule (which the UI already shows).
    # Requirements answers are cited facts (or already LLM-generated + grounded
    # in the RAG path), so return them verbatim — never re-phrase (that invents
    # courses).
    if req_block:
        return {"explanation": req_block.rstrip("- \n"),
                "used_llm": bool(state.get("llm_understood")), "llm_explained": False}
    return _grounded(pin_note + (
        "Your plan is above. Tell me what to change (e.g. \"make 2A lighter\", "
        "\"no music in 1A\", \"swap CS 486 for CS 480\"), ask about a course, or say **help**."
    ))
