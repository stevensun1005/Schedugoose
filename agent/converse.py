"""Natural-language chat during onboarding (Groq-first, not form scripts)."""

from __future__ import annotations

import json
from typing import Any

from agent.intake import next_question
from agent.llm import complete_text, llm_available
from agent.state import PlannerState, last_user_message
from agent.understand import understanding_from_state

_SYSTEM = """You are Schedugoose, a friendly University of Waterloo course-planning assistant.
Talk like a real advisor — warm, concise, not a rigid FAQ bot.

Rules:
- Acknowledge greetings and emotions first (hi, frustration, confusion).
- Early on, find out if they are a brand-new first-year or a returning student. If returning, ask which courses they have already completed (they can paste a list like "CS 135, MATH 135") so the plan skips them. If they are new or say nothing about it, treat them as a fresh first-year — never assume completed courses.
- If Current intake already lists program/residency/sequence/start_term, NEVER ask for them again — only ask what is still missing.
- If the user already has a plan (see note below), do not restart onboarding.
- If the user asks why you're not talking or repeating yourself, apologize briefly and explain you need a few details to build their plan.
- Ask for only ONE missing profile item per reply, conversationally.
- Never paste the same block of text twice in a row; vary your wording.
- Reply in the user's language (English or Chinese).
- 2–4 sentences max. No bullet lists unless the user asked for options.

You cannot build a full plan until profile is complete, but you should still chat naturally."""


def _missing_fields(intake: dict[str, Any]) -> list[str]:
    labels = {
        "program": "program (e.g. Computer Science)",
        "residency": "whether they are an international or domestic student",
        "sequence": "co-op sequence (co-op or regular)",
        "start_term": "start term for 1A (e.g. Fall 2026)",
        "career_goal": "career or field they're aiming for",
    }
    missing: list[str] = []
    for key, label in labels.items():
        if not intake.get(key):
            missing.append(label)
    return missing


def _format_history(messages: list[dict[str, str]], limit: int = 8) -> str:
    lines: list[str] = []
    for msg in messages[-limit:]:
        role = msg.get("role", "user")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {msg.get('content', '')}")
    return "\n".join(lines)


def _fallback_reply(state: PlannerState) -> str:
    intake = state.get("intake") or {}
    config = state.get("config") or {}
    nq = next_question(intake, config)

    if state.get("llm_offline"):
        if intake.get("program"):
            return f"Got it — **{intake['program']}**. {nq}" if nq else f"Got it — **{intake['program']}**."
        if intake.get("career_goal"):
            return f"Sounds like you're aiming for **{intake['career_goal']}**. {nq}" if nq else "Building your plan."
        return (
            "Groq is busy or rate-limited — I parsed what I could. "
            + (nq or "Tell me a bit more about your program and goals.")
        )

    user = last_user_message(state).lower().strip()
    from agent.career import parse_career_goal

    if parse_career_goal(last_user_message(state), intake):
        cg = parse_career_goal(last_user_message(state), intake)
        return f"Got it — aiming for **{cg}**. Building your plan now."

    if any(g in user for g in ("hi", "hello", "hey", "你好", "嗨")):
        if not intake.get("program"):
            return (
                "Hey! I'm Schedugoose — I help UW students map out their whole co-op sequence. "
                "What program are you in?"
            )
        return "Hey! Good to see you — tell me what you'd like to adjust in your plan."

    if any(p in user for p in ("why", "not talking", "not respond", "为什么不", "怎么不")):
        return (
            "Sorry — I wasn't ignoring you! I need your program and a few basics before I can "
            "build a real plan. What are you studying at UW?"
        )

    return nq or "What would you like help with?"


def conversational_reply(state: PlannerState) -> tuple[str, bool]:
    """Groq chat reply while intake is incomplete. Returns (text, used_llm)."""

    intake = state.get("intake") or {}
    config = state.get("config") or {}
    user_msg = last_user_message(state)
    messages = state.get("messages") or []
    missing = _missing_fields(intake)
    hint = next_question(intake, config)
    understanding = understanding_from_state(state)
    intent = understanding.intent if understanding else "general"

    if not llm_available():
        return _fallback_reply(state), False

    plan_note = "User already has a generated plan — answer about it, do not re-ask profile basics.\n" if state.get("plan") else ""

    payload = (
        f"Conversation so far:\n{_format_history(messages)}\n\n"
        f"Latest user message:\n{user_msg}\n\n"
        f"{plan_note}"
        f"Detected intent: {intent}\n"
        f"Current intake:\n{json.dumps(intake, indent=2, default=str)}\n\n"
        f"Still missing for planning: {', '.join(missing) if missing else 'nothing — ready to plan'}\n"
        f"Topic hint (rephrase naturally, do NOT copy verbatim):\n{hint}"
    )
    text = complete_text(_SYSTEM, payload)
    if text:
        return text.strip(), True
    return _fallback_reply(state), False


def wants_conversation(state: PlannerState) -> bool:
    """True when we should chat naturally instead of dumping a form question."""

    if not state.get("needs_clarification"):
        return False
    u = understanding_from_state(state)
    if u and u.intent in ("general", "onboarding"):
        return True
    msg = last_user_message(state).lower().strip()
    if len(msg) <= 30 and any(
        g in msg for g in ("hi", "hello", "hey", "why", "你好", "嗨", "吗", "？")
    ):
        return True
    return bool(u and u.intent == "general")
