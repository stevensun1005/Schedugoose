"""Pasted Quest class schedule -> .ics with real rooms as LOCATION."""

from __future__ import annotations

from data.quest_schedule import parse_class_schedule, to_ics

# Synthetic paste mirroring Quest's List View structure (no real personal data).
_PASTE = """My Class Schedule
Spring 2026 | Undergraduate | University of Waterloo
CO 327 - Deter OR Models (Non-Spec)
Status\tUnits\tGrading\tGrade\tDeadlines
Enrolled
0.50
Class Nbr\tSection\tComponent\tDays & Times\tRoom\tInstructor\tStart/End Date
3775
001
LEC
MW 1:00PM - 2:20PM
QNC 2501
A Instructor
05/11/2026 - 08/05/2026
STAT 337 - Intro Biostatistics
Class Nbr\tSection\tComponent\tDays & Times\tRoom\tInstructor\tStart/End Date
3879
001
LEC
TTh 1:00PM - 2:20PM
MC 2065
B Instructor
05/11/2026 - 08/05/2026
3880
101
TUT
F 1:30PM - 2:20PM
MC 2066
B Instructor
05/11/2026 - 08/05/2026
HRM 200 - Basic Human Resources Mgmt
Class Nbr\tSection\tComponent\tDays & Times\tRoom\tInstructor\tStart/End Date
2384
081
LEC
TBA
ONLN - Online
C Instructor
05/11/2026 - 08/05/2026
"""


def test_parses_courses_meetings_and_rooms() -> None:
    parsed = parse_class_schedule(_PASTE)
    assert parsed["term"] == "Spring 2026"
    by = {c.course_id: c for c in parsed["courses"]}
    co = by["CO 327"].meetings[0]
    assert co.days == ["MO", "WE"] and co.start == "13:00" and co.end == "14:20"
    assert co.room == "QNC 2501"
    assert str(co.date_start) == "2026-05-11" and str(co.date_end) == "2026-08-05"
    # STAT 337 has LEC (TTh) + TUT (F), separate rooms.
    stat = by["STAT 337"].meetings
    assert [m.component for m in stat] == ["LEC", "TUT"]
    assert stat[0].days == ["TU", "TH"] and stat[1].days == ["FR"]
    assert stat[1].room == "MC 2066" and stat[1].start == "13:30"
    # TBA/online rows carry no schedulable meeting.
    assert by["HRM 200"].meetings == []


def test_ics_has_locations_rrules_and_correct_first_dates() -> None:
    ics = to_ics(parse_class_schedule(_PASTE))
    assert "LOCATION:QNC 2501" in ics
    assert "LOCATION:MC 2065" in ics and "LOCATION:MC 2066" in ics
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20260805T235959Z" in ics
    # 2026-05-11 is a Monday -> MW series starts that day; F series starts 05-15.
    assert "DTSTART;TZID=America/Toronto:20260511T130000" in ics
    assert "DTSTART;TZID=America/Toronto:20260515T133000" in ics
    assert "SUMMARY:CO 327 LEC" in ics
    assert "BEGIN:VTIMEZONE" in ics and ics.count("BEGIN:VEVENT") == 3


def test_endpoint_returns_calendar_or_friendly_422() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/schedule.ics", json={"text": _PASTE})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "LOCATION:QNC 2501" in r.text
    r2 = c.post("/schedule.ics", json={"text": "nothing schedulable here"})
    assert r2.status_code == 422
