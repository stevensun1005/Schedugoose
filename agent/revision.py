"""Per-turn plan revision deltas (avoid repeating stale pin notes)."""

from __future__ import annotations

from typing import Any


def revision_delta(
    prev: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Codes added to term_avoid / term_requirements / must_avoid this turn only."""

    prev = prev or {}
    turn_avoid: dict[str, list[str]] = {}
    for slot, codes in (config.get("term_avoid") or {}).items():
        old = set((prev.get("term_avoid") or {}).get(slot, []))
        added = [c for c in codes if c not in old]
        if added:
            turn_avoid[slot] = added

    turn_reqs: dict[str, list[str]] = {}
    for slot, codes in (config.get("term_requirements") or {}).items():
        old = set((prev.get("term_requirements") or {}).get(slot, []))
        added = [c for c in codes if c not in old]
        if added:
            turn_reqs[slot] = added

    old_must = set(prev.get("must_avoid") or [])
    new_must = list(config.get("must_avoid") or [])
    must_added = [c for c in new_must if c not in old_must]

    return {
        "term_avoid": turn_avoid,
        "term_requirements": turn_reqs,
        "must_avoid": must_added,
    }


def _slot_without_course(plan: dict[str, Any], code: str, hint: str) -> str:
    """Best label for where a course was removed (prefer hint if course absent there)."""

    terms = [t for t in plan.get("terms", []) if t.get("kind") != "work"]
    if hint:
        term = next((t for t in terms if t.get("label") == hint), None)
        if term and code not in (term.get("courses") or []):
            return hint
    for t in terms:
        if code not in (t.get("courses") or []):
            return str(t.get("label") or "")
    return hint


def format_turn_revision_note(delta: dict[str, Any], plan: dict[str, Any]) -> str:
    """Short note for changes made **this turn** only."""

    if not plan:
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for code in delta.get("must_avoid") or []:
        if code not in seen:
            lines.append(f"Removed **{code}** from your plan.")
            seen.add(code)

    for slot, codes in sorted((delta.get("term_avoid") or {}).items()):
        for code in codes:
            if code in seen:
                continue
            label = _slot_without_course(plan, code, slot)
            if label:
                lines.append(f"Excluded **{code}** from {label}.")
            else:
                lines.append(f"Excluded **{code}**.")
            seen.add(code)

    for slot, codes in sorted((delta.get("term_requirements") or {}).items()):
        term = next((t for t in plan.get("terms", []) if t.get("label") == slot), None)
        if not term:
            continue
        courses = set(term.get("courses") or [])
        for code in codes:
            if " " not in str(code):
                continue
            if code in courses:
                lines.append(f"Scheduled **{code}** in {slot}.")
            else:
                lines.append(f"Could not fit **{code}** in {slot} (prereqs or schedule).")

    return "\n".join(lines) + ("\n\n" if lines else "")
