"""Enrollment restrictions: "<program> students only" (hard constraint H6).

UW lists program restrictions in the same ``requirementsDescription`` field as
prerequisites, e.g. STAT 206 ("Statistics for Software Engineering") says
*"Prereq: MATH 115, 119; Software Eng students only."* — that course must never
be planned for a Computer Science student.

The classifier is deliberately ordered so a *program* restriction is never
mistaken for a broader *faculty* one: "Software Engineering" is the SE program,
not every Engineering student; "Computer Science" is the CS program, not every
Science student.
"""

from __future__ import annotations

import re

# Captures the program phrase in "... <phrase> students only", anchored to a
# clause boundary so the "Prereq: ..." prefix is not swept in.
_ONLY_RE = re.compile(
    r"(?:^|[;.,]|\band\b)\s*([A-Za-z][A-Za-z/&,\-\s]*?)\s+students?\s+only",
    re.IGNORECASE,
)


def restriction_from_requirements(req_desc: str) -> list[str]:
    """Extract program-restriction phrases from a requirements description."""

    if not req_desc:
        return []
    phrases = [m.strip(" .,;") for m in _ONLY_RE.findall(req_desc)]
    # Dedupe, keep order, drop empties.
    seen: list[str] = []
    for p in phrases:
        if p and p.lower() not in {s.lower() for s in seen}:
            seen.append(p)
    return seen


def _classify(phrase: str) -> tuple[str, str]:
    """Map a restriction phrase to a ('program'|'faculty'|'unknown', value).

    Specific programs are checked before the faculties they live under, so
    "Software Eng" resolves to the SE *program* rather than the Engineering
    faculty, and "Computer Science" to the CS program rather than Science.
    """

    p = phrase.lower()
    if "software eng" in p:
        return ("program", "software engineering")
    if "computer eng" in p:
        return ("program", "computer engineering")
    if "computer science" in p:
        return ("program", "computer science")
    if "knowledge integration" in p or re.search(r"\bscience\b", p):
        return ("faculty", "science")
    if "mathematics" in p or re.search(r"\bmath\b", p):
        return ("faculty", "math")
    if re.search(r"\beng(ineering)?\b", p):
        return ("faculty", "engineering")
    if "arts" in p or "accounting" in p or "afm" in p:
        return ("faculty", "arts")
    return ("unknown", p)


def student_eligible(
    restricted_to: list[str] | None,
    program: str | None,
    faculty: str | None,
) -> bool:
    """True when a student in ``program`` / ``faculty`` may take the course.

    Open courses (no restriction) are always eligible. When the student's
    program is unknown we do not over-filter. A restricted course is eligible
    only when one of its restriction phrases names the student's program or
    faculty; an unrecognized phrase is treated conservatively (not eligible).
    """

    if not restricted_to:
        return True
    prog = (program or "").strip().lower()
    fac = (faculty or "").strip().lower()
    if not prog and not fac:
        return True  # unknown student — can't judge, don't drop the course

    for phrase in restricted_to:
        kind, val = _classify(phrase)
        if kind == "program" and prog and (val in prog or prog in val):
            return True
        if kind == "faculty" and fac and val == fac:
            return True
    return False
