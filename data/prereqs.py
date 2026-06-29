"""Parse UW ``requirementsDescription`` into planner prereq codes."""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"\b([A-Za-z]{2,5})\s+(\d{3})([A-Za-z]?)\b")


def normalize_prereq_code(subject: str, catalog: str, suffix: str = "") -> str:
    """Drop lab suffixes like 136L → CS 136 for scheduling."""

    code = f"{subject.upper()} {catalog.upper()}{suffix.upper()}"
    m = re.match(r"^([A-Z]+ \d{3})[A-Z]$", code)
    return m.group(1) if m else code


def prereqs_from_requirements(description: str | None) -> list[str]:
    """Best-effort parse of UW prereq text (first OR-branch, AND within branch)."""

    if not description:
        return []
    body = description.strip()
    if body.lower().startswith("prereq"):
        body = re.sub(r"^prereq:\s*", "", body, flags=re.I)
    body = body.split("Antireq")[0].split("Coreq")[0]

    branches = re.split(r"\)\s*or\s*\(|\s+or\s+", body, flags=re.I)
    branch = branches[0].strip("() ")
    out: list[str] = []
    for subj, num, suf in _CODE_RE.findall(branch):
        code = normalize_prereq_code(subj, num, suf)
        if code not in out:
            out.append(code)
    return out
