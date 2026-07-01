"""Parse UW ``requirementsDescription`` into planner prereq codes."""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"\b([A-Za-z]{2,5})\s+(\d{3})([A-Za-z]?)\b")
# Subjects are UPPERCASE in UW requirement text (CS, MATH, STAT); matching only
# uppercase keeps connector words ("and", "of", "One") from being read as a
# subject when a bare number inherits it. Mirrors UWFlow's SubjectRegexp.
_SUBJECT_RE = re.compile(r"\b[A-Z]{2,5}\b")
_NUMBER_RE = re.compile(r"\b\d{3}[A-Za-z]?\b")


def normalize_prereq_code(subject: str, catalog: str, suffix: str = "") -> str:
    """Drop lab suffixes like 136L → CS 136 for scheduling."""

    code = f"{subject.upper()} {catalog.upper()}{suffix.upper()}"
    m = re.match(r"^([A-Z]+ \d{3})[A-Z]$", code)
    return m.group(1) if m else code


def expand_course_codes(text: str) -> list[str]:
    """Expand course codes, carrying a subject across listed numbers.

    UW lists alternatives/lists with the subject stated once, e.g.
    ``"One of CS 240, 245, 246"`` or ``"MATH 135/137"``. A bare number
    inherits the most recent subject, so all of CS 240 / CS 245 / CS 246 are
    recovered. Mirrors UWFlow's importer ``expandCourseCodes``.
    """

    tokens = sorted(
        [(m.start(), "subject", m.group()) for m in _SUBJECT_RE.finditer(text)]
        + [(m.start(), "number", m.group()) for m in _NUMBER_RE.finditer(text)]
    )
    out: list[str] = []
    last_subject: str | None = None
    for _, kind, value in tokens:
        if kind == "subject":
            last_subject = value
        elif last_subject is not None:
            num, suf = value[:3], value[3:]
            code = normalize_prereq_code(last_subject, num, suf)
            if code not in out:
                out.append(code)
    return out


def antireqs_from_requirements(description: str | None) -> list[str]:
    """Parse the ``Antireq:`` clause into course codes (mutually-exclusive)."""

    if not description:
        return []
    m = re.search(r"antireq[a-z]*\s*:?\s*(.+)", description, flags=re.I)
    if not m:
        return []
    # Antireqs run to the next section header or end of string.
    body = re.split(r"\b(?:prereq|coreq)[a-z]*\s*:", m.group(1), flags=re.I)[0]
    return expand_course_codes(body)


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
    codes = expand_course_codes(branch)
    # "One of A, B, C" is an alternative list (any one suffices); a strict-AND
    # planner should require only the first, not all of them.
    if codes and re.search(r"\b(?:one|1|two|2)\s+of\b", branch, flags=re.I):
        return codes[:1]
    return codes
