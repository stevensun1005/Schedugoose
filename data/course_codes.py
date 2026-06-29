"""Resolve subject abbreviations to course codes in the catalog."""

from __future__ import annotations

from data.mock_data import MOCK_ROWS
from data.uw_api import fetch_courses

# Spoken names → UW subject codes
_SUBJECT_ALIASES: dict[str, str] = {
    "MUSIC": "MUSIC",
    "MUSI": "MUSIC",
    "MUS": "MUSIC",
    "ENGL": "ENGL",
    "ENGLISH": "ENGL",
    "ECON": "ECON",
    "ECONOMICS": "ECON",
    "STAT": "STAT",
    "STATS": "STAT",
    "MATH": "MATH",
    "CS": "CS",
}


def normalize_subject(subject: str) -> str:
    key = subject.strip().upper()
    return _SUBJECT_ALIASES.get(key, key)


def course_ids_for_subject(subject: str) -> list[str]:
    """All catalog course ids for a subject, e.g. ENGL → ENGL 119, ENGL 129."""

    subj = normalize_subject(subject)
    prefix = f"{subj} "
    ids: list[str] = []
    seen: set[str] = set()

    for row in MOCK_ROWS:
        cid = row["course_id"]
        if cid.startswith(prefix) and cid not in seen:
            ids.append(cid)
            seen.add(cid)

    try:
        for course in fetch_courses():
            if course.course_id.startswith(prefix) and course.course_id not in seen:
                ids.append(course.course_id)
                seen.add(course.course_id)
    except Exception:
        pass

    return ids
