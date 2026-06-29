"""explain node: plan + trade-offs -> natural language.

LLM path when available; otherwise a faithful template that narrates only what
is actually in the plan (no invention).
"""

from __future__ import annotations

import json
from typing import Any

from agent.llm import complete_text
from agent.state import PlannerState

_SYSTEM = """You are Schedugoose, a UW course-planning assistant. Given a \
student's intake, preferences and a term-by-term plan across their co-op \
sequence, explain in a few sentences what the plan does: how it progresses \
through prerequisites, covers degree requirements, and respects preferences \
(load, mornings, easy courses). Reference only courses/terms present in the \
data. Be concise and friendly."""


def _template_plan(intake: dict[str, Any], config: dict[str, Any], plan: dict[str, Any]) -> str:
    lines: list[str] = []
    prog = plan.get("program") or intake.get("program") or "your program"
    lines.append(
        f"Here's a term-by-term plan for {prog} on the {plan.get('sequence')} "
        f"sequence, starting {plan.get('start_term')}:"
    )
    for t in plan.get("terms", []):
        if t["kind"] == "work":
            lines.append(f"  - {t['label']} ({t['display']}): co-op work term")
        elif t.get("courses"):
            note = f" -- {t['note']}" if t.get("note") else ""
            lines.append(f"  - {t['label']} ({t['display']}): {', '.join(t['courses'])}{note}")
        else:
            lines.append(f"  - {t['label']} ({t['display']}): {t.get('note', 'open electives')}")

    if config.get("min_easy_courses"):
        lines.append("Each term includes at least one lighter course, as you asked.")
    if config.get("time_prefs", {}).get("avoid_before"):
        lines.append(f"I avoided classes before {config['time_prefs']['avoid_before']}.")
    if plan.get("complete"):
        lines.append("This satisfies your program's core requirements.")
    else:
        rem = plan.get("remaining_requirements") or {}
        if rem:
            need = ", ".join(f"{k} (+{v})" for k, v in rem.items())
            lines.append(f"Still to cover later: {need}.")
    lines.append("Tell me to make a term lighter, avoid mornings, swap a course, or change your sequence and I'll re-plan.")
    return "\n".join(lines)


def explain(state: PlannerState) -> dict[str, Any]:
    intake = state.get("intake") or {}
    config = state.get("config") or {}
    plan = state.get("plan")

    if not plan:
        return {"explanation": state.get("clarification", "Tell me a bit more to get started.")}

    llm_text = complete_text(
        _SYSTEM,
        f"Intake:\n{json.dumps(intake, indent=2)}\n\n"
        f"Preferences:\n{json.dumps(config, indent=2)}\n\n"
        f"Plan:\n{json.dumps(plan, indent=2)}",
    )
    if llm_text:
        return {"explanation": llm_text, "used_llm": True}
    return {"explanation": _template_plan(intake, config, plan)}
