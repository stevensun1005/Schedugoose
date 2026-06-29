"""Shared planner state passed between LangGraph nodes."""

from __future__ import annotations

from typing import Any, TypedDict

from scheduler.types import Course


class Profile(TypedDict, total=False):
    completed: list[str]   # transcript: completed course codes
    program: str           # program / specialization key
    term: str              # target term code


class PlannerState(TypedDict, total=False):
    messages: list[dict[str, str]]   # [{"role": ..., "content": ...}]
    profile: Profile
    intake: dict[str, Any]           # onboarding: program/sequence/start_term/career
    career_goal: str
    config: dict[str, Any] | None    # LLM-produced solver config (README JSON shape)
    candidates: list[Course]         # pre-filtered, relevance-scored courses
    schedule: dict[str, Any] | None  # ScheduleResult.as_dict() (single-term)
    plan: dict[str, Any] | None      # multi-term sequence plan
    needs_clarification: bool
    clarification: str               # question to ask the user
    explanation: str                 # natural-language narration
    used_llm: bool                   # whether a real LLM was used this turn


def last_user_message(state: PlannerState) -> str:
    for msg in reversed(state.get("messages", [])):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
