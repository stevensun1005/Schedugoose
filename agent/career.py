"""Career-goal parsing (short replies like ``ds`` → data science)."""

from __future__ import annotations

import re

from agent.semantic import has_career_hint
from data.sequences import parse_start_term

_ALIASES: dict[str, str] = {
    "ds": "data science",
    "data": "data science",
    "data sci": "data science",
    "data science": "data science",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "swe": "software engineering",
    "se": "software engineering",
    "be": "backend engineering",
    "backend": "backend engineering",
    "fe": "frontend development",
    "frontend": "frontend development",
    "sec": "security",
    "security": "security",
    "cyber": "cybersecurity",
    "quant": "quantitative finance",
    "pm": "product management",
}


def parse_career_goal(text: str, intake: dict | None = None) -> str | None:
    """Map shorthand or short answers to a career goal string."""

    raw = text.strip()
    low = raw.lower()
    if parse_start_term(text) or re.search(r"(fall|winter|spring)\s*\d{4}", low):
        return None
    if low in _ALIASES:
        return _ALIASES[low]

    if has_career_hint(raw):
        return raw

    intake = intake or {}
    only_career_missing = (
        intake.get("program")
        and intake.get("residency")
        and intake.get("sequence")
        and intake.get("start_term")
        and not intake.get("career_goal")
    )
    if only_career_missing and 1 <= len(low) <= 30:
        if low in ("yes", "no", "y", "n"):
            return None
        return raw

    return None
