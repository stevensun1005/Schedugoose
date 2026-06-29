"""Shared planner state passed between LangGraph nodes."""

from __future__ import annotations

from typing import Any, TypedDict

from scheduler.types import Course


class Profile(TypedDict, total=False):
    completed: list[str]   # transcript: completed course codes
    program: str           # program / specialization key
    term: str              # target term code


class PlannerState(TypedDict, total=False):
    messages: list[dict[str, str]]
    profile: Profile
    intake: dict[str, Any]
    career_goal: str
    config: dict[str, Any] | None
    # OR pipeline (Phase 2 LangGraph nodes)
    catalog: list[Course]
    candidates: list[Course]
    conflicts: list[tuple[str, str]]
    model_ready: bool
    current_term: str
    schedule: dict[str, Any] | None
    plan: dict[str, Any] | None
    infeasible: bool
    diagnosis: list[str]
    last_solve_status: str
    # RAG + agent trace (resume-visible)
    rag_hits: list[dict[str, Any]]
    grounded_codes: list[str]
    graph_trace: list[str]
    understanding: dict[str, Any] | None
    turn_revision: dict[str, Any] | None
    # Dialogue
    needs_clarification: bool
    # True when this turn answers a pending onboarding question (so a bare
    # course code is treated as an answer, not a course lookup).
    answering_onboarding: bool
    clarification: str
    explanation: str
    used_llm: bool
    llm_understood: bool
    llm_explained: bool


def last_user_message(state: PlannerState) -> str:
    for msg in reversed(state.get("messages", [])):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
