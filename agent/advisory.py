"""Conversational plan advice — recommendations and explanations (not template dumps)."""

from __future__ import annotations

import json
from typing import Any

from agent.llm import complete_text, llm_available
from agent.state import PlannerState, last_user_message

_SYSTEM = """You are Schedugoose, a University of Waterloo course-planning advisor.
The user ALREADY has a term-by-term plan visible in the UI.

Your job: answer their question conversationally — course recommendations, why courses \
were placed, trade-offs for their career goal.

Rules:
- NEVER paste the full term-by-term schedule (no bullet list of every term).
- Mention specific course codes from their plan or RAG suggestions when relevant.
- If they ask for data science / ML / stats paths, highlight STAT, CS 486, CS 480, MATH 239, etc. when appropriate.
- If they say you are not explaining or to stop using templates, apologize briefly and give a real answer.
- 3–8 sentences unless they asked for a short list of recommendations.
- Reply in the user's language (English or Chinese)."""


def compact_plan_summary(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    for term in plan.get("terms", []):
        if term.get("kind") == "work":
            continue
        courses = term.get("courses") or []
        if courses:
            lines.append(f"{term.get('label')}: {', '.join(courses)}")
    return "\n".join(lines[:16])


def _rag_block(state: PlannerState) -> str:
    hits = state.get("rag_hits") or []
    if not hits:
        return ""
    h = hits[0]
    courses = ", ".join(h.get("courses") or [])[:400]
    return (
        f"Career KB ({h.get('career')}): suggested courses include {courses}. "
        f"Skills: {', '.join(h.get('skills') or [])}."
    )


def _fallback_advisory(state: PlannerState) -> str:
    intake = state.get("intake") or {}
    career = intake.get("career_goal") or state.get("career_goal") or "your goals"
    rag = _rag_block(state)
    plan = state.get("plan") or {}
    ds_courses = [
        c
        for t in plan.get("terms", [])
        for c in (t.get("courses") or [])
        if c.startswith(("STAT ", "CS 4", "CS 3", "MATH 239"))
    ]
    picked = list(dict.fromkeys(ds_courses))[:8]
    if picked:
        return (
            f"For **{career}**, your plan already includes {', '.join(picked)}. "
            f"{rag} Ask me about a specific term if you want to swap something."
        ).strip()
    return (
        f"I'd focus electives on stats and ML courses for **{career}** "
        f"(e.g. STAT 230/231/341, CS 486, CS 480). {rag}"
    ).strip()


def advisory_reply(state: PlannerState) -> tuple[str, bool]:
    """Natural-language advice when a plan exists. Returns (text, used_llm)."""

    if not llm_available():
        return _fallback_advisory(state), False

    intake = state.get("intake") or {}
    plan = state.get("plan") or {}
    user_msg = last_user_message(state)
    messages = state.get("messages") or []
    history = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in messages[-8:]
    )

    payload = (
        f"Conversation:\n{history}\n\n"
        f"Latest user message:\n{user_msg}\n\n"
        f"Career goal: {intake.get('career_goal') or state.get('career_goal') or 'unknown'}\n"
        f"Program: {intake.get('program')}\n\n"
        f"Plan summary (do NOT repeat verbatim as a full schedule):\n{compact_plan_summary(plan)}\n\n"
        f"{_rag_block(state)}"
    )
    text = complete_text(_SYSTEM, payload)
    if text:
        return text.strip(), True
    return _fallback_advisory(state), False
