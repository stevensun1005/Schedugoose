"""Semantic layer: natural language -> structured solver config.

Two paths, same output shape (the README JSON config):

1. **LLM path** (when ``ANTHROPIC_API_KEY`` is set): structured output.
2. **Rule-based fallback**: deterministic few-shot-style phrase anchors, so the
   system runs and is testable with no LLM key.

The LLM/fallback only ever *translates* fuzzy language into weights and
categories -- it never computes the schedule and never invents course codes
(career->courses is grounded by the RAG knowledge base downstream).
"""

from __future__ import annotations

import re
from typing import Any

from agent.llm import complete_json
from data.program_reqs import get_program_reqs

# Course-code matcher, e.g. "cs486", "CS 486", "stat 341".
_COURSE_RE = re.compile(r"\b([A-Za-z]{2,4})\s?([0-9]{3}[A-Za-z]?)\b")

_DEFAULT_WEIGHTS = {"career": 0.5, "easy": 0.3, "prof": 0.2, "morning": 0.0, "friday": 0.0}


def normalize_course_code(raw: str) -> str:
    m = _COURSE_RE.search(raw)
    if not m:
        return raw.strip().upper()
    return f"{m.group(1).upper()} {m.group(2).upper()}"


def extract_course_codes(text: str) -> list[str]:
    return [f"{s.upper()} {n.upper()}" for s, n in _COURSE_RE.findall(text)]


# --------------------------------------------------------------------------- #
# Rule-based fallback
# --------------------------------------------------------------------------- #
_LIGHT_PHRASES = [
    "light", "manageable", "chill", "relaxed", "not too much", "not too hard",
    "not too heavy", "not too intense", "not too challenging", "nothing too hard",
    "not hard", "easygoing", "take it easy", "go easy",
]
# "hard" deliberately excluded (negated forms like "not too hard" are light).
_INTENSE_PHRASES = [
    "intense", "challenge", "challenging", "heavy", "rigorous", "max out",
    "push myself", "really hard", "very hard", "as hard as", "hardest",
]


def _apply_intensity(text: str, weights: dict[str, float], credit: dict[str, float]) -> None:
    light = any(k in text for k in _LIGHT_PHRASES)
    intense = (not light) and any(k in text for k in _INTENSE_PHRASES)
    if light:
        weights["easy"] = 0.5
        weights["career"] = 0.4
        weights["prof"] = 0.1
        credit["min"], credit["max"] = 2.0, 2.5
    if intense:
        weights["career"] = 0.6
        weights["easy"] = 0.1
        weights["prof"] = 0.3
        credit["min"], credit["max"] = 2.5, 3.0


def _to_units(amount: float, kind: str) -> float:
    """Normalize a quantity to credits. A UW course is 0.5 credits."""

    return amount * 0.5 if "course" in kind else amount


def _apply_credit_cap(text: str, credit: dict[str, float]) -> None:
    """Parse explicit load phrasing, e.g. 'under 2.0 credits', '5 courses a term'."""

    # "<= N courses/credits"
    m = re.search(r"(?:under|below|at most|max(?:imum)?|no more than|less than|only|just)\s*([0-9]+(?:\.[0-9]+)?)\s*(credit|unit|course|class)", text)
    if m:
        cap = _to_units(float(m.group(1)), m.group(2))
        credit["max"] = cap
        credit["min"] = min(credit.get("min", cap), cap)
    # ">= N courses/credits"
    m = re.search(r"(?:at least|min(?:imum)?|no less than)\s*([0-9]+(?:\.[0-9]+)?)\s*(credit|unit|course|class)", text)
    if m:
        floor = _to_units(float(m.group(1)), m.group(2))
        credit["min"] = floor
        credit["max"] = max(credit.get("max", floor), floor)
    # bare "N courses (a term)" -> treat as an exact target
    m = re.search(r"\b([1-7])\s*(course|class)e?s?\b(?!\s*(?:relevant|like))", text)
    if m and "at least" not in text and "least" not in text:
        units = _to_units(float(m.group(1)), m.group(2))
        credit["min"] = units
        credit["max"] = units


def _wants_easy_course(text: str) -> int:
    """Detect 'at least one easy course' style requests; return required count."""

    if re.search(r"(?:at least|include|want)\s*(?:one|1|a|an|some)\s*easy", text):
        return 1
    if "easy course" in text or "easy class" in text or "bird course" in text:
        return 1
    return 0


def _apply_time_prefs(text: str) -> tuple[dict[str, Any], float, float]:
    time_prefs: dict[str, Any] = {}
    morning_w = 0.0
    friday_w = 0.0
    # "no early", "no mornings", "not before 10"
    m = re.search(r"before\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if any(k in text for k in ["no morning", "no early", "not early", "avoid morning", "late start", "no 8", "no 9"]):
        time_prefs["avoid_before"] = "10:00"
        morning_w = 0.5
    if m:
        hour = int(m.group(1))
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        time_prefs["avoid_before"] = f"{hour:02d}:{m.group(2) or '00'}"
        morning_w = max(morning_w, 0.5)
    if "friday" in text and any(k in text for k in ["free", "off", "no", "avoid", "clear", "without"]):
        time_prefs["avoid_friday"] = True
        friday_w = 0.4
    return time_prefs, morning_w, friday_w


def rule_based_config(text: str, program: str, prev: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic NL -> config. Builds the README config JSON shape."""

    low = text.lower()
    weights = dict((prev or {}).get("weights", _DEFAULT_WEIGHTS))
    credit = dict((prev or {}).get("credit_load", {"min": 2.0, "max": 2.5}))

    _apply_intensity(low, weights, credit)
    _apply_credit_cap(low, credit)
    time_prefs, morning_w, friday_w = _apply_time_prefs(low)
    weights["morning"] = morning_w
    weights["friday"] = friday_w

    # Explicit course intents.
    must_include = list((prev or {}).get("must_include", []))
    must_avoid = list((prev or {}).get("must_avoid", []))
    include_trigger = any(k in low for k in ["must take", "must include", "include", "definitely", "i need", "all of them"])
    avoid_codes = {
        normalize_course_code(m.group(1))
        for m in re.finditer(r"(?:avoid|skip|don'?t want|drop)\s+([A-Za-z]{2,4}\s?[0-9]{3}[A-Za-z]?)", low)
    }
    for code in avoid_codes:
        if code not in must_avoid:
            must_avoid.append(code)
    if include_trigger:
        for code in extract_course_codes(text):
            if code not in avoid_codes and code not in must_include:
                must_include.append(code)

    min_easy = max(int((prev or {}).get("min_easy_courses", 0)), _wants_easy_course(low))

    return {
        "target_categories": list((prev or {}).get("target_categories", [])),
        "credit_load": credit,
        "weights": weights,
        "time_prefs": time_prefs,
        "must_include": must_include,
        "must_avoid": must_avoid,
        "program_reqs": (prev or {}).get("program_reqs") or get_program_reqs(program),
        "min_easy_courses": min_easy,
    }


# --------------------------------------------------------------------------- #
# Public entrypoint (LLM with rule-based fallback)
# --------------------------------------------------------------------------- #
_SYSTEM = """You translate a student's natural-language course-planning request \
into a JSON solver config. You never invent course codes. Output keys: \
target_categories (list of strings), credit_load ({min,max} floats), \
weights ({career,easy,prof,morning,friday} floats 0-1), \
time_prefs ({avoid_before "HH:MM", avoid_friday bool}), \
must_include (list of course codes), must_avoid (list of course codes). \
Map vague phrasing: "keep it light" -> easy~0.5; "I want a challenge" -> \
career~0.6, easy~0.1; "no early classes" -> morning~0.5 and avoid_before 10:00."""


def to_config(text: str, program: str, prev: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
    """Return (config, used_llm). Falls back to rules when the LLM is unavailable."""

    fallback = rule_based_config(text, program, prev)
    llm = complete_json(_SYSTEM, f"Program: {program}\nPrevious config: {prev}\nRequest: {text}")
    if not llm:
        return fallback, False
    # Merge: trust LLM for translation fields, keep program reqs grounded.
    merged = dict(fallback)
    for key in ("target_categories", "credit_load", "weights", "time_prefs",
                "must_include", "must_avoid", "min_easy_courses"):
        if key in llm:
            merged[key] = llm[key]
    return merged, True


# --------------------------------------------------------------------------- #
# Clarification detection
# --------------------------------------------------------------------------- #
_CAREER_HINTS = ["scientist", "engineer", "developer", "researcher", "analyst",
                 "ai", "ml", "data", "security", "backend", "frontend", "career",
                 "become", "want to be", "aiming"]

_CLARIFY_QUESTION = (
    "What career or field are you aiming for (e.g. data scientist, "
    "backend engineer, security)? That drives which courses I prioritize."
)


def has_career_hint(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in _CAREER_HINTS)


def needs_clarification(text: str, config: dict[str, Any], established: bool = False) -> tuple[bool, str]:
    """Flag missing info the planner needs before it can plan.

    ``established`` is True once a career has been set earlier in the session
    (so revision turns like "make it lighter" don't re-trigger clarification).
    """

    if established or has_career_hint(text) or config.get("must_include"):
        return False, ""
    return True, _CLARIFY_QUESTION
