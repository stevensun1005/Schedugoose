"""LLM-first turn understanding: Groq interprets the user, code fetches API data."""

from __future__ import annotations

import json
from typing import Any

from agent.intent_schema import VALID_MINORS, TurnUnderstanding
from agent.llm import complete_structured, llm_available
from agent.semantic import has_career_hint
from agent.state import PlannerState, last_user_message
from data.degree_plans import SPECIALIZATIONS, DegreePlan, plan_from_intake, plan_to_dict
from data.sequences import identify_program, match_sequence

# Phrases that show the user is volunteering a career goal (so an LLM-extracted
# career is grounded, not assumed).
_CAREER_INTENT = (
    "want to", "wanna", "i want", "i'd like", "interested in", "aspire",
    "looking to", "career in", "work in", "aiming", "become", "goal is",
    "hoping to", "dream", "into ", "focus on",
)


def _user_stated_career(text: str, career_goal: str | None) -> bool:
    """True only when the user actually expressed a career this turn."""

    low = (text or "").lower()
    if has_career_hint(low):
        return True
    cg = (career_goal or "").strip().lower()
    if cg and cg in low:
        return True
    return any(p in low for p in _CAREER_INTENT)

_SYSTEM = """You are the understanding layer for Schedugoose, a University of Waterloo course planner.

You receive the FULL conversation plus current intake state. Interpret the LATEST user \
message in context — never rely on fixed keyword lists.

Return structured JSON only.

**Intent** (pick one)
- course_lookup: what is / tell me about a specific course
- requirements_qa: degree or specialization requirements
- plan_revision: change schedule, term placement, avoid courses, load, times
- career_advice: recommend courses, explain why the plan looks this way, career path Q&A
- onboarding: profile info ONLY when intake is still missing fields
- general: greetings, meta chat, frustration, "explain" without changing the schedule

**If intake is already complete** (no missing fields), NEVER use onboarding — use career_advice or general even if they mention program/residency again.
- Read earlier turns: if the user already said CS / international / co-op, fill those intake fields — do not ask again.

**Critical — infer missing intake fields from context**
- Read which intake fields are still empty. The latest message is often answering \
the assistant's last question.
- If only career_goal is missing, ANY reply (ds, quant, PM, games, "something with robots") \
is the career — expand shorthand into a clear phrase in career_goal (e.g. ds → data science).
- Do NOT require exact keywords. Use world knowledge for abbreviations and typos.
- program, residency, sequence, start_term: extract when the user states them in any wording.

**Plan revision**
- term_requirements: pin courses to terms, e.g. {"2A": ["CS 245", "CS 246"]}
- term_avoid: exclude courses from a term, e.g. {"2A": ["CS 240"]}
- Subject without number: "no engl in 2A" → list all ENGL courses in term_avoid for that term
- "want X instead" → add X to the term mentioned earlier in the message

**Other**
- Never invent course codes not implied by the user.
- suggested_electives: courses fitting their stated goals; empty if unknown.
- solver.*: scheduling preferences (light load, no mornings, etc.)."""


def _format_history(messages: list[dict[str, str]], limit: int = 12) -> str:
    lines: list[str] = []
    for msg in messages[-limit:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def _missing_intake_fields(intake: dict[str, Any]) -> list[str]:
    return [k for k in ("program", "residency", "sequence", "start_term", "career_goal") if not intake.get(k)]


def understand_turn(text: str, state: PlannerState) -> tuple[TurnUnderstanding | None, bool]:
    """Groq structured understanding of the full conversation. Returns (result, used_llm)."""

    if not llm_available():
        return None, False

    intake = state.get("intake") or {}
    prev_config = state.get("config") or {}
    messages = state.get("messages") or []
    missing = _missing_intake_fields(intake)

    payload = (
        f"Conversation:\n{_format_history(messages)}\n\n"
        f"Latest user message:\n{text}\n\n"
        f"Intake fields still missing: {', '.join(missing) if missing else 'none'}\n\n"
        f"Current intake:\n{json.dumps(intake, indent=2, default=str)}\n\n"
        f"Current config:\n{json.dumps(prev_config, indent=2, default=str)}"
    )
    result = complete_structured(_SYSTEM, payload, TurnUnderstanding)
    return result, result is not None


def _user_asked_degree_plan(text: str) -> bool:
    low = text.lower()
    return any(
        k in low
        for k in (
            "specialization",
            "specialisation",
            " spec",
            "minor",
            "double major",
            "triple major",
            "business spec",
            "hci",
            "computational math",
            "artificial intelligence",
        )
    )


def apply_understanding(
    intake: dict[str, Any],
    understanding: TurnUnderstanding,
    *,
    text: str = "",
) -> dict[str, Any]:
    """Merge LLM-extracted profile fields into intake (trust the model, no keyword remap)."""

    out = dict(intake)

    if understanding.program and not out.get("program"):
        prog = identify_program(understanding.program)
        if prog:
            out["program"] = prog.name
            out["faculty"] = prog.faculty
            out["reqs_key"] = prog.reqs_key

    if understanding.residency and not out.get("residency"):
        out["residency"] = understanding.residency

    if understanding.sequence and out.get("faculty") and not out.get("sequence"):
        key = match_sequence(understanding.sequence, out["faculty"])
        if not key:
            low = understanding.sequence.lower()
            if "co" in low:
                key = "math-coop" if out.get("faculty") == "Math" else "eng-stream-4"
            elif "regular" in low:
                key = "math-regular" if out.get("faculty") == "Math" else "sci-regular"
        if key:
            out["sequence"] = key

    if understanding.start_term and not out.get("start_term"):
        out["start_term"] = understanding.start_term.model_dump()

    if understanding.career_goal:
        # Accept a career goal only when the user actually expressed one, or when
        # career was the single field still being asked for (so a short reply like
        # "robots" counts). Uses the *pre-update* intake so an assumed goal slipped
        # in alongside another answer (e.g. the start-term turn) is rejected.
        asked_for_career = (
            intake.get("program") and intake.get("residency")
            and intake.get("sequence") and intake.get("start_term")
            and not intake.get("career_goal")
        )
        if _user_stated_career(text, understanding.career_goal) or asked_for_career:
            out["career_goal"] = understanding.career_goal.strip()

    specs = [s for s in understanding.specializations if s in SPECIALIZATIONS]
    minors = [m for m in understanding.minors if m in VALID_MINORS]
    if (specs or minors) and _user_asked_degree_plan(text):
        base = plan_from_intake(out)
        kind = "major_specialization" if specs else ("major_minor" if minors else base.kind)
        dp = DegreePlan(
            kind=kind,
            primary=out.get("reqs_key") or base.primary,
            specializations=tuple(specs) if specs else base.specializations,
            minors=tuple(minors) if minors else base.minors,
            extra_majors=base.extra_majors,
        )
        out["degree_plan"] = plan_to_dict(dp)

    return out


def understanding_from_state(state: PlannerState) -> TurnUnderstanding | None:
    raw = state.get("understanding")
    if not raw:
        return None
    try:
        return TurnUnderstanding.model_validate(raw)
    except Exception:
        return None


def wants_course_lookup(state: PlannerState) -> bool:
    u = understanding_from_state(state)
    if u:
        return u.intent == "course_lookup"
    if llm_available():
        return False
    from agent.course_qa import is_course_info_question

    return is_course_info_question(last_user_message(state))


def wants_requirements_qa(state: PlannerState) -> bool:
    u = understanding_from_state(state)
    if u:
        return u.intent == "requirements_qa"
    if llm_available():
        return False
    from agent.requirements_qa import is_requirements_question

    return is_requirements_question(last_user_message(state))


def wants_plan_revision(state: PlannerState) -> bool:
    u = understanding_from_state(state)
    if u:
        return u.intent == "plan_revision"
    return False


def wants_career_advice(state: PlannerState) -> bool:
    u = understanding_from_state(state)
    if u:
        return u.intent == "career_advice"
    return False


_ADVISORY_HINTS = (
    "recommend", "suggest", "explain", "why", "how come", "what course",
    "which course", "walk me through", "help me understand", "any course",
    "courses you", "course you", "relating to", "don't use template",
    "dont use template", "not explaining", "you are not explaining",
)


def wants_advisory_reply(state: PlannerState) -> bool:
    """Conversational answer about the plan — not a schedule dump."""

    if not state.get("plan"):
        return False
    if wants_course_lookup(state) or wants_requirements_qa(state) or wants_plan_revision(state):
        return False
    if wants_career_advice(state):
        return True
    u = understanding_from_state(state)
    if u and u.intent == "general":
        return True
    msg = last_user_message(state).lower()
    return any(h in msg for h in _ADVISORY_HINTS)


def should_replan(state: PlannerState) -> bool:
    """Skip expensive re-solve when the user only wants an explanation."""

    from agent.intake import is_complete

    intake = state.get("intake") or {}
    if not is_complete(intake, state.get("config")):
        return False
    # Onboarding just completed and there is no plan yet — always build the
    # first plan, even when the closing turn is labelled "onboarding".
    if not state.get("plan"):
        return True
    if wants_advisory_reply(state):
        if wants_career_advice(state) or wants_plan_revision(state):
            return True
        return False
    u = understanding_from_state(state)
    if u and u.intent == "onboarding":
        return False
    return True


def course_codes_for_lookup(state: PlannerState) -> list[str]:
    u = understanding_from_state(state)
    if u and u.course_codes:
        return u.course_codes
    from agent.semantic import extract_course_codes

    return extract_course_codes(last_user_message(state))
