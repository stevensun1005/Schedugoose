"""UW Open Data API v3 wrapper + normalization.

Live path: ``/Courses/{term}/{subject}`` + ``/ClassSchedules/{term}/{subject}/{catalog}``.
Prereq/category/easiness tags are enriched from the bundled mock catalog when available.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from data.cache import get_or_set
from data.prereqs import antireqs_from_requirements, prereq_groups_from_requirements, prereqs_from_requirements
from data.restrictions import restriction_from_requirements
from data.mock_data import MOCK_ROWS, RawRow
from data.term_codes import term_code_from_start
from scheduler.types import Course, Section, TimeSlot, hhmm_to_minutes

API_BASE = "https://openapi.data.uwaterloo.ca/v3"
_CACHE_TTL_S = 60 * 60

_last_data_source: str = "mock"
MOCK_BY_ID: dict[str, RawRow] = {r["course_id"]: r for r in MOCK_ROWS}

# Short blurbs when live API description is unavailable (mock-only runs).
_MOCK_DESCRIPTIONS: dict[str, str] = {
    "SOC 101": (
        "An introduction to sociological concepts and interpretation — communities, "
        "institutions, social processes, and change, with emphasis on Canadian society."
    ),
}

_COURSE_ID_RE = re.compile(r"^([A-Za-z]{2,5})\s+(\d{3}[A-Za-z]?)$")


def data_source() -> str:
    """``live`` | ``mock`` | ``live+mock-fallback`` — set by the last :func:`fetch_courses`."""

    return _last_data_source


def _set_source(src: str) -> None:
    global _last_data_source
    _last_data_source = src


def _normalize_meeting(m: dict) -> TimeSlot:
    return TimeSlot(
        weekdays=m["weekdays"],
        start=hhmm_to_minutes(m["start"]),
        end=hhmm_to_minutes(m["end"]),
    )


def normalize_rows(rows: list[RawRow]) -> list[Course]:
    by_course: dict[str, Course] = {}
    for r in rows:
        cid = r["course_id"]
        course = by_course.get(cid)
        if course is None:
            restricted = list(r.get("restricted_to", [])) or restriction_from_requirements(
                r.get("requirements_description", "")
            )
            antireqs = list(r.get("antireqs", [])) or antireqs_from_requirements(
                r.get("requirements_description", "")
            )
            # OR-alternatives: explicit on the row, else parsed from the UW
            # requirements text ("CS 136 or CS 146"), else flat AND.
            groups = list(r.get("prereq_groups", [])) or prereq_groups_from_requirements(
                r.get("requirements_description", "")
            )
            course = Course(
                course_id=cid,
                title=r.get("title", cid),
                units=float(r.get("units", 0.5)),
                prereqs=list(r.get("prereqs", [])),
                prereq_groups=groups,
                antireqs=antireqs,
                categories=list(r.get("categories", [])),
                easiness=float(r.get("easiness", 0.0)),
                prof_rating=float(r.get("prof_rating", 0.0)),
                restricted_to=restricted,
                sections=[],
            )
            by_course[cid] = course
        sections = [
            Section(
                course_id=cid,
                component=r.get("component", "LEC"),
                section_code=r.get("section_code", "LEC 001"),
                times=tuple(_normalize_meeting(m) for m in r.get("meetings", [])),
                instructor=r.get("instructor", ""),
                term=r.get("term", ""),
                cap=int(r.get("cap", 0)),
                enrolled=int(r.get("enrolled", 0)),
            )
        ]
        if not sections[0].times:
            sections[0] = Section(
                course_id=cid,
                component=r.get("component", "LEC"),
                section_code=r.get("section_code", "LEC 001"),
                times=(TimeSlot("MWF", 600, 660),),
                instructor=r.get("instructor", ""),
                term=r.get("term", ""),
                cap=int(r.get("cap", 120)),
                enrolled=int(r.get("enrolled", 0)),
            )
        course.sections.extend(sections)
    return list(by_course.values())


def _enrich_row(row: RawRow) -> RawRow:
    mock = MOCK_BY_ID.get(row["course_id"])
    if not mock:
        return row
    out = dict(row)
    out["prereqs"] = list(mock.get("prereqs", []))
    out["categories"] = list(mock.get("categories", out.get("categories", [])))
    out["easiness"] = float(mock.get("easiness", 0.5))
    out["prof_rating"] = float(mock.get("prof_rating", 0.6))
    return RawRow(**out)  # type: ignore[arg-type]


def _map_class_sections(
    classes: list[dict],
    *,
    subject: str,
    catalog: str,
    title: str,
    term: str,
) -> list[RawRow]:
    course_id = f"{subject} {catalog}"
    rows: list[RawRow] = []
    for entry in classes:
        comp = entry.get("courseComponent", "LEC")
        sec = entry.get("classSection", "001")
        scheds = entry.get("scheduleData") or []
        if not scheds:
            rows.append(_enrich_row(RawRow(
                course_id=course_id, title=title, units=0.5,
                component=comp, section_code=f"{comp} {sec}",
                term=term,
                cap=int(entry.get("maxEnrollmentCapacity", 0) or 120),
                enrolled=int(entry.get("enrolledStudents", 0) or 0),
                meetings=[{"weekdays": "MWF", "start": "10:00", "end": "11:20"}],
            )))
            continue
        for sched in scheds:
            days = sched.get("classMeetingDayPatternCode") or "MWF"
            start = (sched.get("classMeetingStartTime") or "")[11:16]
            end = (sched.get("classMeetingEndTime") or "")[11:16]
            meetings = [{"weekdays": days, "start": start, "end": end}] if start and end else []
            rows.append(_enrich_row(RawRow(
                course_id=course_id, title=title, units=0.5,
                component=comp, section_code=f"{comp} {sec}",
                term=term,
                cap=int(entry.get("maxEnrollmentCapacity", 0) or 120),
                enrolled=int(entry.get("enrolledStudents", 0) or 0),
                meetings=meetings,
            )))
    return rows


def _undergrad_catalog(catalog: str) -> bool:
    if not re.fullmatch(r"\d{3}[A-Z]?", catalog):
        return False
    return 100 <= int(re.match(r"\d+", catalog).group()) < 500  # type: ignore[union-attr]


def _fetch_live(term: str, subjects: list[str]) -> list[RawRow]:
    """Fetch course offerings (metadata) — one request per subject.

    Section times are taken from the bundled mock catalog when available, to
    stay within UW API rate limits (per-catalog ClassSchedule calls are expensive).
    """

    key = os.environ["UW_API_KEY"]
    headers = {"x-api-key": key, "accept": "application/json"}
    rows: list[RawRow] = []
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=30.0) as client:
        for subject in subjects:
            resp = client.get(f"/Courses/{term}/{subject}")
            resp.raise_for_status()
            for course in resp.json():
                career = course.get("associatedAcademicCareer", "")
                if career and career not in ("UG", "UGRD", "UNDG", "Undergraduate"):
                    continue
                catalog = str(course.get("catalogNumber", ""))
                if not _undergrad_catalog(catalog):
                    continue
                course_id = f"{subject} {catalog}"
                title = course.get("title", course_id)
                req_desc = course.get("requirementsDescription") or ""
                live_prereqs = prereqs_from_requirements(req_desc)
                mock = MOCK_BY_ID.get(course_id)
                if mock:
                    row = dict(mock)
                    row["title"] = title
                    row["term"] = term
                    if live_prereqs:
                        row["prereqs"] = live_prereqs
                    if req_desc:
                        row["requirements_description"] = req_desc
                    rows.append(RawRow(**row))  # type: ignore[arg-type]
                else:
                    cats = [f"{subject}-{catalog[0]}xx"]
                    # Math-faculty 300/400-level → "Math-3xx" requirement bucket
                    if subject in {"MATH", "STAT", "CO", "AMATH", "PMATH", "ACTSC"} and catalog[:1] in ("3", "4"):
                        cats.append("Math-3xx")
                    rows.append(RawRow(
                        course_id=course_id,
                        title=title,
                        units=0.5,
                        prereqs=live_prereqs,
                        categories=cats,
                        component="LEC",
                        section_code="LEC 001",
                        term=term,
                        cap=120,
                        enrolled=0,
                        meetings=[{"weekdays": "MWF", "start": "10:00", "end": "11:20"}],
                        easiness=0.5,
                        prof_rating=0.6,
                        restricted_to=restriction_from_requirements(req_desc),
                        requirements_description=req_desc,
                    ))
    return rows


def uw_api_status() -> str:
    """Probe UW API once so /health reflects live vs mock (not stale default)."""

    if not os.getenv("UW_API_KEY"):
        return "mock (no UW_API_KEY)"
    try:
        fetch_courses(term=term_code_from_start(None), subjects=["CS"])
        return data_source()
    except Exception:
        return "mock+fallback"


def fetch_courses(
    term: str | None = None,
    subjects: list[str] | None = None,
    *,
    start_term: dict | None = None,
) -> list[Course]:
    """Return normalized courses. Uses UW OpenAPI when ``UW_API_KEY`` is set."""

    term = term or term_code_from_start(start_term)
    # Cover the whole Math faculty plus the elective/comm subjects the planner
    # leans on — a Math Studies / ActSci student's eligible pool must include
    # PMATH/AMATH/ACTSC, not just the CS-adjacent core.
    subjects = subjects or [
        "CS", "STAT", "MATH", "CO", "PMATH", "AMATH", "ACTSC",
        "ECON", "AFM", "ENGL", "COMMST", "SPCOM", "EMLS",
    ]

    if not os.getenv("UW_API_KEY"):
        _set_source("mock")
        return normalize_rows(MOCK_ROWS)

    cache_key = f"uw:v2:{term}:{','.join(sorted(subjects))}"

    def _producer() -> list[RawRow]:
        return _fetch_live(term, subjects)

    try:
        rows = get_or_set(cache_key, _CACHE_TTL_S, _producer)
        if not rows:
            _set_source("mock")
            return normalize_rows(MOCK_ROWS)
        # Merge mock-only courses needed for planning (PD, some electives).
        live_ids = {r["course_id"] for r in rows}
        extras = [r for r in MOCK_ROWS if r["course_id"] not in live_ids]
        _set_source("live")
        return normalize_rows(rows + extras)  # type: ignore[arg-type]
    except Exception:
        _set_source("live+mock-fallback")
        return normalize_rows(MOCK_ROWS)


def lookup_course(
    course_id: str,
    *,
    start_term: dict | None = None,
) -> dict[str, Any]:
    """Fetch one course's title and description (UW Open Data ``/Courses``)."""

    m = _COURSE_ID_RE.match(course_id.strip())
    if not m:
        return {"course_id": course_id.strip().upper(), "error": "invalid course code", "source": "none"}

    subject, catalog = m.group(1).upper(), m.group(2).upper()
    normalized = f"{subject} {catalog}"
    mock = MOCK_BY_ID.get(normalized)

    def _from_mock() -> dict[str, Any]:
        return {
            "course_id": normalized,
            "title": mock["title"] if mock else normalized,
            "description": _MOCK_DESCRIPTIONS.get(normalized),
            "units": float(mock.get("units", 0.5)) if mock else 0.5,
            "prereqs": list(mock.get("prereqs", [])) if mock else [],
            "categories": list(mock.get("categories", [])) if mock else [],
            "restricted_to": list(mock.get("restricted_to", [])) if mock else [],
            "requirements_description": mock.get("requirements_description", "") if mock else "",
            # True = confirmed exists; None = couldn't check; False = checked & absent.
            "found": True if mock else None,
            "source": "mock",
        }

    if not os.getenv("UW_API_KEY"):
        return _from_mock()

    term = term_code_from_start(start_term)
    cache_key = f"uw:course:{term}:{normalized}"

    def _fetch_live() -> dict[str, Any]:
        key = os.environ["UW_API_KEY"]
        headers = {"x-api-key": key, "accept": "application/json"}
        with httpx.Client(base_url=API_BASE, headers=headers, timeout=30.0) as client:
            resp = client.get(f"/Courses/{term}/{subject}")
            resp.raise_for_status()
            for course in resp.json():
                if str(course.get("catalogNumber", "")).upper() != catalog:
                    continue
                career = course.get("associatedAcademicCareer", "")
                if career and career not in ("UG", "UGRD", "UNDG", "Undergraduate"):
                    continue
                out = _from_mock()
                out["title"] = course.get("title", out["title"])
                out["description"] = course.get("description") or out.get("description")
                out["found"] = True
                req_desc = course.get("requirementsDescription") or ""
                if req_desc:
                    out["requirements_description"] = req_desc
                    parsed = prereqs_from_requirements(req_desc)
                    if parsed:
                        out["prereqs"] = parsed
                    restricted = restriction_from_requirements(req_desc)
                    if restricted:
                        out["restricted_to"] = restricted
                out["source"] = "live"
                return out
        # Queried the live API and the course wasn't in that subject → absent,
        # unless the bundled catalog knows it.
        out = _from_mock()
        out["found"] = True if mock else False
        out["source"] = "live+mock-fallback"
        return out

    try:
        return get_or_set(cache_key, _CACHE_TTL_S, _fetch_live)
    except Exception:
        out = _from_mock()
        out["source"] = "mock+fallback"
        return out


def offered_seasons_map(start: dict | None = None) -> dict[str, set[str]]:
    """course_id -> seasons it is actually offered in ("Fall"/"Winter"/"Spring").

    Live only: queries the Courses endpoint once per season (cached) around the
    student's start term and unions the results — so the planner can refuse to
    place a fall-only course in a Spring slot. Offline (no UW_API_KEY) returns
    {} and no filtering happens (the bundled catalog carries no offering data;
    inventing it would be fabrication).
    """

    if not os.getenv("UW_API_KEY"):
        return {}
    from data.term_codes import resolve_uw_term_code

    base = start or {"season": "Fall", "year": 2026}
    year = int(base.get("year", 2026))
    out: dict[str, set[str]] = {}
    for season in ("Fall", "Winter", "Spring"):
        # Winter/Spring of the academic year following a Fall start.
        y = year if season == "Fall" else year + 1
        code = resolve_uw_term_code(season, y) or resolve_uw_term_code(season, year)
        if not code:
            continue
        try:
            for c in fetch_courses(term=code):
                out.setdefault(c.course_id, set()).add(season)
        except Exception:
            continue
    # If only one season could be fetched, the map would wrongly claim
    # everything is single-season — require at least two for filtering.
    seasons_seen = {s for v in out.values() for s in v}
    return out if len(seasons_seen) >= 2 else {}


def _fetch_schedule_rows(code: str, subject: str, catalog: str, title: str) -> list[RawRow]:
    """One /ClassSchedules call -> RawRows with real meeting times (cached)."""

    key = os.environ["UW_API_KEY"]
    headers = {"x-api-key": key, "accept": "application/json"}
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=15.0) as client:
        resp = client.get(f"/ClassSchedules/{code}/{subject}/{catalog}")
        if resp.status_code != 200:
            return []
        return _map_class_sections(
            resp.json(), subject=subject, catalog=catalog, title=title, term=code,
        )


def attach_live_sections(courses: list[Course], season: str, year: int, cap: int = 20) -> list[Course]:
    """Swap mock meeting times for REAL section schedules where UW publishes them.

    Bounded by design: only terms whose code resolves (UW publishes ~2-3 terms
    ahead — far-future terms keep representative times), at most ``cap`` courses
    per term, every call cached. Offline or with SCHEDUGOOSE_LIVE_SECTIONS=0
    this is a no-op, so tests stay deterministic.
    """

    from dataclasses import replace as _dc_replace

    if not os.getenv("UW_API_KEY") or os.getenv("SCHEDUGOOSE_LIVE_SECTIONS", "1") == "0":
        return courses
    from data.term_codes import resolve_uw_term_code

    code = resolve_uw_term_code(season, year)
    if not code:
        return courses

    out: list[Course] = []
    fetched = 0
    for c in courses:
        m = _COURSE_ID_RE.match(c.course_id)
        if m is None or fetched >= cap:
            out.append(c)
            continue
        subject, catalog = m.group(1).upper(), m.group(2)

        def _producer(subject: str = subject, catalog: str = catalog, title: str = c.title) -> list[RawRow]:
            try:
                return _fetch_schedule_rows(code, subject, catalog, title)
            except Exception:
                return []

        try:
            rows = get_or_set(f"uw:sched:v1:{code}:{c.course_id}", _CACHE_TTL_S * 6, _producer)
        except Exception:
            rows = []
        fetched += 1
        real = [r for r in rows if r.get("meetings")]
        if real:
            sections = list(normalize_rows(real)[0].sections)
            # Prefer sections with seats left (attach runs after prefilter, so
            # this is the only spot that sees real enrollment); if everything
            # is full, keep them all — a waitlist beats silently dropping the course.
            open_secs = [s for s in sections if s.has_space]
            out.append(_dc_replace(c, sections=open_secs or sections))
        else:
            out.append(c)  # keep representative times rather than dropping the course
    return out
