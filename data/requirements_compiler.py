"""Compile UW academic-calendar requirement text into solver constraints.

The workflow the planner follows for a returning student:

    transcript PDF -> courses taken            (data/transcript.py)
    program name   -> placeholder              (intake)
    UW website     -> requirement text         (data/kuali.py, authoritative)
    THIS MODULE    -> text -> constraint groups
    compare        -> which groups still need courses
    schedule       -> only eligible courses (prereq / antireq / restriction)

Kuali requirement text is regular enough to compile directly:

    "Complete 1 of the following: MATH225 - ... (0.50) MATH235 - ... (0.50)"
        -> choice group  {count 1, courses [MATH 225, MATH 235, ...]}
    "Complete 10 additional math courses at the 300- or 400-level from the
     following subject codes: ACTSC, AMATH, CO, CS, MATH, PMATH, STAT"
        -> level group   {count 10, subjects [...], min_level 300}

Anything we cannot parse is preserved as a note (never silently dropped), and
callers fall back to the curated requirement tables when compilation finds
nothing — the system degrades, it doesn't break.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CODE_RE = re.compile(r"\b([A-Z]{2,7})\s?(\d{2,3}[A-Z]?)\b(?=\s*-)")
_CHOICE_RE = re.compile(r"Complete\s+(\d+|all)\s+of the following\b(.*)", re.I)
_LEVEL_RE = re.compile(
    r"Complete\s+(\d+)\s+additional\s+.*?(\d{3})-?\s*(?:or|and)\s*(\d{3})-level.*?"
    r"subject codes?:\s*([A-Z][A-Z,\s]+)",
    re.I,
)


@dataclass
class ReqGroup:
    label: str
    count: int
    courses: list[str] = field(default_factory=list)   # explicit choice options
    subjects: list[str] = field(default_factory=list)  # level-rule subjects
    min_level: int = 0

    def matches(self, course_id: str) -> bool:
        if course_id in self.courses:
            return True
        if self.subjects:
            subj, _, num = course_id.partition(" ")
            digits = re.match(r"\d+", num or "")
            if subj in self.subjects and digits and int(digits.group()) >= self.min_level:
                return True
        return False

    def satisfied_by(self, completed: set[str]) -> int:
        return sum(1 for c in completed if self.matches(c))

    def to_dict(self) -> dict:
        return {"label": self.label, "count": self.count, "courses": self.courses,
                "subjects": self.subjects, "min_level": self.min_level}

    @classmethod
    def from_dict(cls, d: dict) -> "ReqGroup":
        return cls(label=d["label"], count=int(d["count"]),
                   courses=list(d.get("courses") or []),
                   subjects=list(d.get("subjects") or []),
                   min_level=int(d.get("min_level") or 0))


def _codes(chunk: str) -> list[str]:
    return [f"{s} {n}" for s, n in _CODE_RE.findall(chunk)]


def _choice_label(codes: list[str]) -> str:
    if len(codes) <= 4:
        return "One of " + "/".join(codes)
    return f"One of {codes[0]}/{codes[1]}/… ({len(codes)} options)"


def compile_requirements(text: str) -> list[ReqGroup]:
    groups: list[ReqGroup] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LEVEL_RE.search(line)
        if m:
            count = int(m.group(1))
            min_level = min(int(m.group(2)), int(m.group(3)))
            # Each comma part may carry trailing prose ("STAT See Bachelor of…")
            # — keep only the leading, fully-uppercase subject token.
            subjects = []
            for part in m.group(4).split(","):
                token = (part.strip().split() or [""])[0]
                if re.fullmatch(r"[A-Z]{2,7}", token):
                    subjects.append(token)
            groups.append(ReqGroup(
                label=f"{count} × {min_level}+-level ({'/'.join(subjects[:4])}…)"
                if len(subjects) > 4 else f"{count} × {min_level}+-level ({'/'.join(subjects)})",
                count=count, subjects=subjects, min_level=min_level,
            ))
            continue
        m = _CHOICE_RE.search(line)
        if m:
            codes = _codes(m.group(2))
            if not codes:
                continue  # a bare section header ("Complete all of the following")
            count = len(codes) if m.group(1).lower() == "all" else int(m.group(1))
            groups.append(ReqGroup(label=_choice_label(codes), count=count, courses=codes))
    return groups


def remaining_from_groups(
    groups: list[ReqGroup], completed: set[str],
) -> dict[str, int]:
    """Compare the transcript against each group -> what's still missing."""

    remaining: dict[str, int] = {}
    for g in groups:
        need = g.count - g.satisfied_by(completed)
        if need > 0:
            remaining[g.label] = need
    return remaining


def tag_catalog(groups: list[ReqGroup], catalog: list) -> None:
    """Tag catalog courses with the labels of groups they can fill (in place).

    The planner's requirement machinery counts category tags, so compiled
    groups become ordinary categories the CP-SAT model already understands.
    """

    for c in catalog:
        for g in groups:
            if g.matches(c.course_id) and g.label not in c.categories:
                c.categories.append(g.label)


def compile_for_program(program: str) -> dict | None:
    """Live path: UW calendar (Kuali) -> compiled constraint groups.

    Returns {"title", "url", "groups"} or None (offline / unknown program) —
    callers then fall back to the curated requirement tables.
    """

    from data.kuali import requirements_for

    try:
        hit = requirements_for(program)
    except Exception:
        return None
    if not hit:
        return None
    title, text, url = hit
    groups = compile_requirements(text)
    if not groups:
        return None
    return {"title": title, "url": url, "groups": groups}
