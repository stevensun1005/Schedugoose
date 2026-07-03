"""Degree audit: requirement-by-requirement checklist against the transcript.

Two questions, both answered as a literal checklist (never LLM-rephrased —
requirement facts must stay exact):

1. "check my degree / am I on track / 帮我check一下"
   -> every graduation requirement of the student's program, one line each,
      ✅ (with the taken courses that satisfy it) or ❌ (what's missing, plus
      eligible course recommendations to fill it).

2. "if I add a statistics minor / AI specialization, what else do I need?"
   -> fetch THAT plan's requirements (UW calendar via Kuali), diff against the
      transcript, list the gaps and recommend eligible courses.

Requirement sources, in order: live-compiled Kuali groups already on the
intake, a fresh Kuali fetch, then the curated category tables (offline).
"""

from __future__ import annotations

import re
from typing import Any

from agent.state import PlannerState, last_user_message
from data.requirements_compiler import ReqGroup, compile_for_program
from data.restrictions import student_eligible
from data.uw_api import fetch_courses

_AUDIT_PHRASES = (
    "check my degree", "check my requirements", "check my progress", "degree audit",
    "audit my", "am i on track", "requirements have i met", "requirements i met",
    "check if i can graduate", "can i graduate", "help me check", "check for me",
    "帮我check", "帮我查", "检查一下", "查一下我的", "毕业条件", "毕业要求",
)
# What-if: naming a plan component + asking what's still missing for it.
_WHATIF_NEED = (
    "what else", "still need", "what do i need", "what courses do i need",
    "am i missing", "what am i missing", "还缺", "还需要", "缺什么", "需要什么课",
)
_WHATIF_TARGET = ("minor", "specializ", "specialis", "major", "option", "diploma")


def _low(state: PlannerState) -> str:
    return last_user_message(state).lower()


def wants_degree_audit(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in _AUDIT_PHRASES)


def wants_component_whatif(state: PlannerState) -> bool:
    low = _low(state)
    return any(t in low for t in _WHATIF_TARGET) and any(n in low for n in _WHATIF_NEED)


def _completed_set(state: PlannerState) -> set[str]:
    intake = state.get("intake") or {}
    profile = state.get("profile") or {}
    return set(profile.get("completed") or []) | set(intake.get("completed") or [])


class _CategoryGroup:
    """Adapter: a curated category requirement quacks like a compiled ReqGroup."""

    def __init__(self, label: str, count: int, catalog: dict[str, Any]):
        self.label, self.count, self._catalog = label, count, catalog

    def matches(self, course_id: str) -> bool:
        c = self._catalog.get(course_id)
        return bool(c) and self.label in c.categories

    def satisfied_by(self, completed: set[str]) -> int:
        return sum(1 for c in completed if self.matches(c))


def _eligible_options(group: Any, completed: set[str], catalog: dict[str, Any],
                      intake: dict[str, Any], limit: int = 6) -> list[str]:
    """Courses that could fill the group and that THIS student may take now."""

    out: list[str] = []
    for cid, c in sorted(catalog.items()):
        if cid in completed or not group.matches(cid):
            continue
        if not student_eligible(c.restricted_to, intake.get("program"), intake.get("faculty")):
            continue
        if any(a in completed for a in c.antireqs):
            continue
        from data.prefilter import prereqs_met

        if not prereqs_met(c, completed):
            continue
        pre = f" (prereq: {', '.join(c.prereqs)})" if c.prereqs else ""
        out.append(f"{cid}{pre}")
        if len(out) >= limit:
            break
    return out


def _checklist(groups: list[Any], completed: set[str], catalog: dict[str, Any],
               intake: dict[str, Any]) -> tuple[list[str], int]:
    lines: list[str] = []
    missing_total = 0
    for g in groups:
        got = sorted(c for c in completed if g.matches(c))
        need = g.count - len(got)
        if need <= 0:
            shown = ", ".join(got[: max(g.count, 1)])
            lines.append(f"✅ {g.label} — satisfied by {shown}")
        else:
            missing_total += need
            have = f" ({len(got)} of {g.count} done: {', '.join(got)})" if got else ""
            lines.append(f"❌ {g.label} — need {need} more{have}")
            opts = _eligible_options(g, completed, catalog, intake)
            if opts:
                lines.append(f"     you could take: {'; '.join(opts)}")
    return lines, missing_total


def _groups_for_program(intake: dict[str, Any]) -> tuple[list[Any], str | None, str | None]:
    """(groups, title, source_url) — live Kuali first, curated fallback."""

    catalog = {c.course_id: c for c in fetch_courses()}
    live = intake.get("live_reqs") or {}
    if live.get("groups"):
        return ([ReqGroup.from_dict(g) for g in live["groups"]],
                live.get("title"), live.get("url"))
    if intake.get("program"):
        fresh = compile_for_program(intake["program"])
        if fresh:
            return fresh["groups"], fresh["title"], fresh["url"]
    # Curated category table fallback (offline).
    from data.degree_plans import MAJORS

    reqs = MAJORS.get(intake.get("reqs_key") or "", {})
    groups = [_CategoryGroup(cat, n, catalog) for cat, n in reqs.items()]
    return groups, intake.get("program"), None


def _in_progress_note(intake: dict[str, Any], completed: set[str]) -> str:
    """Honesty footnote: in-progress courses count above but aren't passed yet."""

    in_prog = [c for c in (intake.get("in_progress") or []) if c in completed]
    if not in_prog:
        return ""
    return (f"\nNote: {', '.join(in_prog)} are in progress this term — "
            "they're counted above but still need a passing grade.")


def degree_audit_reply(state: PlannerState) -> str | None:
    intake = state.get("intake") or {}
    completed = _completed_set(state)
    if not completed:
        return ("I don't have your transcript yet — upload it with 📎 or paste your "
                "completed courses, and I'll check every graduation requirement for you.")
    groups, title, url = _groups_for_program(intake)
    if not groups:
        return None
    catalog = {c.course_id: c for c in fetch_courses()}
    lines, missing = _checklist(groups, completed, catalog, intake)
    head = f"**{title or 'Your program'}** — requirement checklist against your transcript:"
    tail = ("\n🎉 Every requirement above is covered." if missing == 0
            else f"\nStill missing **{missing}** course(s) across the ❌ items above — "
                 "tell me to plan them (or ask about any line).")
    src = f"\nSource: {url}" if url else ""
    return "\n".join([head, *lines]) + tail + _in_progress_note(intake, completed) + src


def component_whatif_reply(state: PlannerState) -> str | None:
    """'If I add a statistics minor, what else do I need?' -> gap checklist."""

    intake = state.get("intake") or {}
    completed = _completed_set(state)
    msg = last_user_message(state)

    # The component being asked about, e.g. "statistics minor", "AI specialization".
    m = re.search(
        r"(?:add|adding|do|pursue|declare|take|get|for)\s+(?:an?\s+)?(.{3,60}?)"
        r"\s*(minor|specialization|specialisation|major|option|diploma)",
        msg, re.I,
    )
    if m:
        target = f"{m.group(1).strip()} {m.group(2)}".strip()
    else:
        # "I want to specialize in business" word order.
        m2 = re.search(r"speciali[sz]e?\s+in\s+([a-z][a-z &-]{2,40})", msg, re.I)
        if not m2:
            return None
        target = f"{m2.group(1).strip()} specialization"

    compiled = compile_for_program(target, context_program=intake.get("program"))
    catalog = {c.course_id: c for c in fetch_courses()}
    if compiled:
        groups, title, url = compiled["groups"], compiled["title"], compiled["url"]
    else:
        # Curated fallback for known CS specializations / minors.
        from data.degree_plans import MINORS, SPECIALIZATIONS, _MINOR_PATTERNS, _SPEC_PATTERNS

        key = None
        low = msg.lower()
        for pat, k in (*_SPEC_PATTERNS, *_MINOR_PATTERNS):
            if re.search(pat, low):
                key = k
                break
        reqs = (SPECIALIZATIONS.get(key) or MINORS.get(key) or {}) if key else {}
        if not reqs:
            return (f"I couldn't find official requirements for **{target}** — "
                    "check the UW calendar: https://uwaterloo.ca/academic-calendar/"
                    "undergraduate-studies/catalog#/programs and tell me the exact plan name.")
        groups = [_CategoryGroup(cat, n, catalog) for cat, n in reqs.items()]
        title, url = key, None

    lines, missing = _checklist(groups, completed, catalog, intake)
    head = f"Adding **{title}** — here's how your transcript measures up:"
    tail = ("\n🎉 You already meet every listed requirement." if missing == 0
            else f"\nYou'd still need **{missing}** more course(s) — the ❌ lines show "
                 "eligible options. Say the word and I'll work them into your plan.")
    src = f"\nSource: {url}" if url else ""
    return "\n".join([head, *lines]) + tail + src


def audit_reply(state: PlannerState) -> str | None:
    """Route both audit shapes; None when this turn isn't an audit question."""

    if wants_degree_audit(state):
        return degree_audit_reply(state)
    if wants_component_whatif(state):
        return component_whatif_reply(state)
    return None
