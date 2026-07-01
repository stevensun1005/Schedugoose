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

from agent.config_schema import SolverConfigOutput
from agent.llm import complete_structured
from data.course_codes import course_ids_for_subject
from data.degree_plans import DOMESTIC_LANGUAGE_CATEGORY, INTL_ENGLISH_CATEGORY, parse_residency
from data.program_reqs import get_program_reqs

# Course-code matcher, e.g. "cs486", "CS 486", "stat 341".
_COURSE_RE = re.compile(r"\b([A-Za-z]{2,5})\s?([0-9]{3}[A-Za-z]?)\b")

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


def _parse_term_requirements(text: str, prev: dict[str, Any] | None) -> dict[str, list[str]]:
    """Per-term constraints, e.g. CS 245 + CS 246 in 2A."""

    low = text.lower()
    term_reqs: dict[str, list[str]] = dict((prev or {}).get("term_requirements") or {})

    def _add(slot: str, code: str) -> None:
        slot = slot.upper()
        code = normalize_course_code(code)
        term_reqs.setdefault(slot, [])
        if code not in term_reqs[slot]:
            term_reqs[slot].append(code)

    first_term = any(k in low for k in (
        "first term", "1a", "first year", "fall term", "my first semester",
    ))
    intl_english = any(k in low for k in (
        "engl 129", "ell", "esl", "english proficiency", "academic english",
        "english language learner", "written english",
    ))
    second_language = any(k in low for k in (
        "french", "german", "spanish", "mandarin", "chinese", "second language",
        "learn a language",
    ))
    generic_language = "language course" in low or (
        "language" in low and not intl_english and not second_language
    )

    if (intl_english or second_language or generic_language) and (
        first_term or "1a" not in term_reqs
    ):
        term_reqs.setdefault("1A", [])
        residency = parse_residency(text)
        if intl_english or residency == "international":
            cat = INTL_ENGLISH_CATEGORY
        elif second_language or residency == "domestic":
            cat = DOMESTIC_LANGUAGE_CATEGORY
        else:
            cat = DOMESTIC_LANGUAGE_CATEGORY
        if cat not in term_reqs["1A"]:
            term_reqs["1A"] = [
                x for x in term_reqs["1A"]
                if x not in (DOMESTIC_LANGUAGE_CATEGORY, INTL_ENGLISH_CATEGORY, "Language")
            ]
            term_reqs["1A"].append(cat)

    # Per-course: "CS 245 in 2A", "add PHIL 145 to 3B", "move CS 246 into 2A"
    for m in re.finditer(
        r"([A-Za-z]{2,4}\s?[0-9]{3}[A-Za-z]?)\s+(?:in|into|for|to)\s+(1[AB]|2[AB]|3[AB]|4[AB])",
        low,
    ):
        _add(m.group(2), m.group(1))

    # Shared term: "cs245 and 246 in 2a", "take CS 245, CS 246 for 2A"
    slot_match = re.search(r"\b(?:in|into|for|to)\s+(1[AB]|2[AB]|3[AB]|4[AB])\b", text, re.I)
    if slot_match:
        slot = slot_match.group(1).upper()
        chunk = text[: slot_match.start()]
        subject = "CS"
        if re.search(r"\bcs\b", chunk, re.I):
            subject = "CS"
        elif re.search(r"\bmath\b", chunk, re.I):
            subject = "MATH"
        elif re.search(r"\bstat\b", chunk, re.I):
            subject = "STAT"
        for part in re.split(r"\band\b|,", chunk, flags=re.I):
            part = part.strip()
            if not part:
                continue
            full = _COURSE_RE.search(part)
            if full:
                _add(slot, f"{full.group(1)} {full.group(2)}")
                subject = full.group(1).upper()
                continue
            bare = re.search(r"\b(\d{3}[A-Za-z]?)\b", part)
            if bare:
                _add(slot, f"{subject} {bare.group(1).upper()}")

    return term_reqs


def _parse_term_avoid(text: str, prev: dict[str, Any] | None) -> dict[str, list[str]]:
    """Per-term exclusions, e.g. don't take CS 240 in 2A."""

    low = text.lower()
    term_avoid: dict[str, list[str]] = dict((prev or {}).get("term_avoid") or {})

    def _avoid(slot: str, code: str) -> None:
        slot = slot.upper()
        code = normalize_course_code(code)
        term_avoid.setdefault(slot, [])
        if code not in term_avoid[slot]:
            term_avoid[slot].append(code)

    for m in re.finditer(
        r"(?:don'?t|do not|not)\s+want(?:\s+to\s+take)?\s+([a-z]{2,4}\s?\d{3}[a-z]?)\s+in\s+(1[ab]|2[ab]|3[ab]|4[ab])",
        low,
    ):
        _avoid(m.group(2), m.group(1))

    for m in re.finditer(
        r"(?:no|avoid|skip|drop|without)\s+([a-z]{2,4}\s?\d{3}[a-z]?)\s+in\s+(1[ab]|2[ab]|3[ab]|4[ab])",
        low,
    ):
        _avoid(m.group(2), m.group(1))

    # Subject-only: "don't want engl in 2a" (no catalog number)
    for m in re.finditer(
        r"(?:don'?t|do not|not)\s+want(?:\s+to\s+take)?\s+([a-z]{2,5})\s+in\s+(1[ab]|2[ab]|3[ab]|4[ab])\b",
        low,
    ):
        subj = m.group(1).upper()
        if re.fullmatch(r"\d{3}", subj):
            continue
        slot = m.group(2).upper()
        for cid in course_ids_for_subject(subj):
            _avoid(slot, cid)

    return term_avoid


def _parse_term_load(text: str, prev: dict[str, Any] | None) -> dict[str, str]:
    """Per-term load intent, e.g. "make 2A lighter" -> {"2A": "light"}.

    Only fires when a term token is present; a bare "make it lighter" is a
    global intensity change handled elsewhere, not a per-term override.
    """

    low = text.lower()
    term_load: dict[str, str] = dict((prev or {}).get("term_load") or {})
    slot = r"(1[ab]|2[ab]|3[ab]|4[ab])"
    word = r"(lighter|heavier|light|heavy)"

    def _apply(s: str, w: str) -> None:
        term_load[s.upper()] = "light" if w.startswith("light") else "heavy"

    # "2a lighter", "make 2a heavier"
    for m in re.finditer(rf"{slot}\D{{0,15}}{word}", low):
        _apply(m.group(1), m.group(2))
    # "lighter 2a", "heavier load in 3b"
    for m in re.finditer(rf"{word}\D{{0,15}}{slot}", low):
        _apply(m.group(2), m.group(1))
    return term_load


def _parse_term_replacements(text: str, term_reqs: dict[str, list[str]]) -> dict[str, list[str]]:
    """'want MATH 237 instead' → pin to the term mentioned earlier in the message."""

    low = text.lower()
    if "instead" not in low:
        return term_reqs

    slots = re.findall(r"\b(1[AB]|2[AB]|3[AB]|4[AB])\b", text, re.I)
    slot = slots[-1].upper() if slots else None
    if not slot:
        return term_reqs

    def _add(code: str) -> None:
        code = normalize_course_code(code)
        term_reqs.setdefault(slot, [])
        if code not in term_reqs[slot]:
            term_reqs[slot].append(code)

    inst = re.search(
        r"want(?:\s+to\s+take)?\s+([a-z]{2,4}\s?\d{3}[a-z]?)\s+instead",
        text,
        re.I,
    )
    if inst:
        _add(inst.group(1))
    return term_reqs

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


def _apply_subject_avoid(low: str, must_avoid: list[str]) -> None:
    """Map 'no music' style phrasing to concrete course codes in the mock catalog."""

    subject_rules: list[tuple[str, list[str]]] = [
        (r"don'?t want (?:to )?(?:learn |take |study |do )?music|no music|not music|without music", ["MUSIC 116"]),
        (r"don'?t want (?:to )?(?:learn |take |study )?anthropology|no anthro", ["ANTH 100"]),
    ]
    for pattern, codes in subject_rules:
        if re.search(pattern, low):
            for code in codes:
                if code not in must_avoid:
                    must_avoid.append(code)


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
    _apply_subject_avoid(low, must_avoid)
    if include_trigger:
        for code in extract_course_codes(text):
            if code not in avoid_codes and code not in must_include:
                must_include.append(code)

    min_easy = max(int((prev or {}).get("min_easy_courses", 0)), _wants_easy_course(low))
    term_requirements = _parse_term_requirements(text, prev)
    term_requirements = _parse_term_replacements(text, term_requirements)
    term_avoid = _parse_term_avoid(text, prev)
    term_load = _parse_term_load(text, prev)

    # Drop avoided courses from pins in the same term.
    for slot, avoid in term_avoid.items():
        if slot in term_requirements:
            term_requirements[slot] = [
                c for c in term_requirements[slot] if c not in avoid
            ]

    return {
        "target_categories": list((prev or {}).get("target_categories", [])),
        "credit_load": credit,
        "weights": weights,
        "time_prefs": time_prefs,
        "must_include": must_include,
        "must_avoid": must_avoid,
        "program_reqs": (prev or {}).get("program_reqs") or get_program_reqs(program),
        "min_easy_courses": min_easy,
        "term_requirements": term_requirements,
        "term_avoid": term_avoid,
        "term_load": term_load,
    }


# --------------------------------------------------------------------------- #
# Public entrypoint (LLM with rule-based fallback)
# --------------------------------------------------------------------------- #
_SYSTEM = """You translate a student's natural-language course-planning request \
into a structured solver config. You never invent course codes — only categories, \
weights, and preferences. Map vague phrasing: "keep it light" -> easy~0.5; \
"I want a challenge" -> career~0.6, easy~0.1; "no early classes" -> morning~0.5 \
and avoid_before "10:00"."""


def to_config(
    text: str,
    program: str,
    prev: dict[str, Any] | None = None,
    *,
    understanding: Any | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return (config, used_llm). LLM understanding preferred; rules when offline."""

    from agent.intent_schema import TurnUnderstanding

    fallback = rule_based_config(text, program, prev)
    reqs = (prev or {}).get("program_reqs") or get_program_reqs(program)

    if isinstance(understanding, TurnUnderstanding):
        merged = dict(fallback)
        llm_dict = understanding.solver.to_solver_dict(program_reqs=reqs)
        for key in ("target_categories", "credit_load", "weights", "time_prefs", "min_easy_courses"):
            if key in llm_dict:
                merged[key] = llm_dict[key]
        for key in ("must_include", "must_avoid"):
            if llm_dict.get(key):
                merged[key] = list(dict.fromkeys((merged.get(key) or []) + llm_dict[key]))
        if understanding.term_requirements:
            tr = dict(merged.get("term_requirements") or {})
            for slot, codes in understanding.term_requirements.items():
                tr.setdefault(slot.upper(), [])
                for code in codes:
                    norm = normalize_course_code(code)
                    if norm not in tr[slot.upper()]:
                        tr[slot.upper()].append(norm)
            merged["term_requirements"] = tr
        if understanding.term_avoid:
            ta = dict(merged.get("term_avoid") or {})
            for slot, codes in understanding.term_avoid.items():
                ta.setdefault(slot.upper(), [])
                for code in codes:
                    norm = normalize_course_code(code)
                    if norm not in ta[slot.upper()]:
                        ta[slot.upper()].append(norm)
            merged["term_avoid"] = ta
            tr = dict(merged.get("term_requirements") or {})
            for slot, avoid in ta.items():
                if slot in tr:
                    tr[slot] = [c for c in tr[slot] if c not in avoid]
            merged["term_requirements"] = tr
        return merged, True

    structured = complete_structured(
        _SYSTEM,
        f"Program: {program}\nPrevious config: {prev}\nRequest: {text}",
        SolverConfigOutput,
    )
    if structured is None:
        return fallback, False
    merged = dict(fallback)
    llm_dict = structured.to_solver_dict(program_reqs=reqs)
    for key in ("target_categories", "credit_load", "weights", "time_prefs", "min_easy_courses"):
        if key in llm_dict:
            merged[key] = llm_dict[key]
    for key in ("must_include", "must_avoid"):
        if key in llm_dict and llm_dict[key]:
            merged[key] = list(dict.fromkeys((merged.get(key) or []) + llm_dict[key]))
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
