"""LLM-as-judge for explanation faithfulness (eval axis 3).

When an API key is configured, a separate LLM call scores whether the
explanation only references courses and terms present in the plan. Without a
key, falls back to the regex checker in ``eval.run_eval``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.llm import complete_json, llm_available

_COURSE_RE = re.compile(r"\b[A-Z]{2,5}\s?[0-9]{3}[A-Za-z]?\b")


def _allowed_courses(plan: dict[str, Any] | None) -> set[str]:
    if not plan:
        return set()
    out: set[str] = set()
    for t in plan.get("terms", []):
        out.update(t.get("courses", []))
    # User-chosen electives are explicit requests, not LLM inventions: an
    # explanation may faithfully name a pick it could not fit into the plan.
    out.update(plan.get("elective_picks", []))
    return {re.sub(r"\s+", " ", c).strip() for c in out}


def rule_based_faithful(explanation: str, plan: dict[str, Any] | None) -> bool:
    mentioned = set(_COURSE_RE.findall(explanation))
    if not mentioned or not plan:
        return True
    allowed = _allowed_courses(plan)
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    return all(norm(m) in allowed for m in mentioned)


_JUDGE_SYSTEM = """You are an eval judge for a course-planning assistant.
Given an explanation and the actual plan JSON, answer with JSON:
{"faithful": true/false, "reason": "one sentence"}
Faithful means every course code mentioned appears in the plan; no invented courses."""


def llm_judge_faithful(explanation: str, plan: dict[str, Any] | None) -> tuple[bool, str]:
    """Return (faithful, reason). Falls back to rules when LLM unavailable."""

    if not explanation or not plan:
        return True, "empty"
    if not llm_available():
        ok = rule_based_faithful(explanation, plan)
        return ok, "rule-based" if ok else "rule-based: invented course code"

    verdict = complete_json(
        _JUDGE_SYSTEM,
        f"Explanation:\n{explanation}\n\nPlan:\n{json.dumps(plan, indent=2)}",
    )
    if not verdict:
        ok = rule_based_faithful(explanation, plan)
        return ok, "rule fallback"
    return bool(verdict.get("faithful", False)), str(verdict.get("reason", ""))
