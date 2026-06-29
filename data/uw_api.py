"""UW Open Data API v3 wrapper + normalization.

Core course data comes from Waterloo's official Open Data API -- fully
sanctioned, no scraping. When ``UW_API_KEY`` is unset, bundled mock data is
used so the system runs offline. Both paths normalize into :class:`Course`.
"""

from __future__ import annotations

import os

import httpx

from data.cache import get_or_set
from data.mock_data import MOCK_ROWS, RawRow
from scheduler.types import Course, Section, TimeSlot, hhmm_to_minutes

API_BASE = "https://openapi.data.uwaterloo.ca/v3"
_CACHE_TTL_S = 60 * 60  # 1 hour -- respect API rate limits


# --------------------------------------------------------------------------- #
# Normalization (shared by mock + live paths)
# --------------------------------------------------------------------------- #
def _normalize_meeting(m: dict) -> TimeSlot:
    return TimeSlot(
        weekdays=m["weekdays"],
        start=hhmm_to_minutes(m["start"]),
        end=hhmm_to_minutes(m["end"]),
    )


def normalize_rows(rows: list[RawRow]) -> list[Course]:
    """Group flat section rows into :class:`Course` objects."""

    by_course: dict[str, Course] = {}
    for r in rows:
        cid = r["course_id"]
        course = by_course.get(cid)
        if course is None:
            course = Course(
                course_id=cid,
                title=r.get("title", cid),
                units=float(r.get("units", 0.5)),
                prereqs=list(r.get("prereqs", [])),
                categories=list(r.get("categories", [])),
                easiness=float(r.get("easiness", 0.0)),
                prof_rating=float(r.get("prof_rating", 0.0)),
                sections=[],
            )
            by_course[cid] = course
        section = Section(
            course_id=cid,
            component=r.get("component", "LEC"),
            section_code=r.get("section_code", "LEC 001"),
            times=tuple(_normalize_meeting(m) for m in r.get("meetings", [])),
            instructor=r.get("instructor", ""),
            term=r.get("term", ""),
            cap=int(r.get("cap", 0)),
            enrolled=int(r.get("enrolled", 0)),
        )
        course.sections.append(section)
    return list(by_course.values())


# --------------------------------------------------------------------------- #
# Live API path (best-effort mapping of the UW v3 schedule schema)
# --------------------------------------------------------------------------- #
_WEEKDAY_FIELDS = [
    ("monday", "M"), ("tuesday", "T"), ("wednesday", "W"),
    ("thursday", "Th"), ("friday", "F"), ("saturday", "Sa"), ("sunday", "Su"),
]


def _map_uw_schedule(raw: list[dict], term: str) -> list[RawRow]:
    """Map UW v3 ``/ClassSchedules`` payloads into our :class:`RawRow` shape."""

    rows: list[RawRow] = []
    for entry in raw:
        subject = entry.get("subjectCode", "")
        catalog = entry.get("catalogNumber", "")
        course_id = f"{subject} {catalog}".strip()
        for sched in entry.get("scheduleData", []) or [{}]:
            days = "".join(
                token for field, token in _WEEKDAY_FIELDS if sched.get(field)
            )
            start = (sched.get("classMeetingStartTime") or "")[11:16]
            end = (sched.get("classMeetingEndTime") or "")[11:16]
            meetings = []
            if days and start and end:
                meetings = [{"weekdays": days, "start": start, "end": end}]
            rows.append(
                RawRow(
                    course_id=course_id,
                    title=entry.get("title", course_id),
                    units=0.5,
                    prereqs=[],
                    categories=[f"{subject}-{catalog[:1]}xx"],
                    component=entry.get("courseComponent", "LEC"),
                    section_code=f"{entry.get('courseComponent', 'LEC')} "
                                 f"{entry.get('classSection', '001')}",
                    instructor="",
                    term=term,
                    cap=int(entry.get("maxEnrollmentCapacity", 0) or 0),
                    enrolled=int(entry.get("enrolledStudents", 0) or 0),
                    meetings=meetings,
                )
            )
    return rows


def _fetch_live(term: str, subjects: list[str]) -> list[RawRow]:
    key = os.environ["UW_API_KEY"]
    headers = {"x-api-key": key, "accept": "application/json"}
    rows: list[RawRow] = []
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=30.0) as client:
        for subject in subjects:
            resp = client.get(f"/ClassSchedules/{term}/{subject}")
            resp.raise_for_status()
            rows.extend(_map_uw_schedule(resp.json(), term))
    return rows


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def fetch_courses(term: str | None = None, subjects: list[str] | None = None) -> list[Course]:
    """Return normalized courses for a term.

    Live when ``UW_API_KEY`` is set (cached to respect rate limits), otherwise
    bundled mock data.
    """

    term = term or os.getenv("DEFAULT_TERM", "1255")
    subjects = subjects or ["CS", "STAT", "MATH", "CO"]

    if not os.getenv("UW_API_KEY"):
        return normalize_rows(MOCK_ROWS)

    cache_key = f"uw:{term}:{','.join(sorted(subjects))}"

    def _producer() -> list[RawRow]:
        return _fetch_live(term, subjects)  # type: ignore[return-value]

    try:
        rows = get_or_set(cache_key, _CACHE_TTL_S, _producer)
        return normalize_rows(rows)  # type: ignore[arg-type]
    except Exception:
        # Network / auth failure -> degrade gracefully to mock data.
        return normalize_rows(MOCK_ROWS)
