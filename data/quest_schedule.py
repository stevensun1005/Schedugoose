"""Parse a pasted Quest "My Class Schedule" page into an .ics calendar.

Students copy their enrolled schedule straight out of Quest (List View). The
paste carries everything a calendar needs — meeting days/times, the REAL room
("QNC 2501"), instructor, and the term's start/end dates — so nothing is
invented: no date, room, or time appears in the .ics that wasn't in the paste.

Quest's meeting rows arrive line-by-line:

    3775            <- class number
    001             <- section
    LEC             <- component
    MW 1:00PM - 2:20PM
    QNC 2501        <- room  (or "ONLN - Online")
    Anteneh Getachew Gebrie
    05/11/2026 - 08/05/2026

"TBA" / online rows have no meeting time and are skipped (an event without a
time would be fabricated).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

_COURSE_RE = re.compile(r"^([A-Z]{2,6}\s?\d{2,3}[A-Z]?)\s*-\s*(.+)$")
_CLASSNBR_RE = re.compile(r"^\d{4,5}$")
_COMPONENTS = {"LEC", "TUT", "LAB", "TST", "SEM", "PRJ", "STU", "WRK", "FLD", "OLN"}
_TIME_RE = re.compile(
    r"^([MTWThFSa]+)\s+(\d{1,2}):(\d{2})(AM|PM)\s*-\s*(\d{1,2}):(\d{2})(AM|PM)$"
)
_DATES_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})$")
_TERM_RE = re.compile(r"\b(Fall|Winter|Spring)\s+(20\d\d)\b")

# Quest day letters -> iCalendar BYDAY codes + Python weekday numbers (Mon=0).
_DAY_TOKENS = [("Th", "TH", 3), ("Su", "SU", 6), ("Sa", "SA", 5),
               ("M", "MO", 0), ("T", "TU", 1), ("W", "WE", 2), ("F", "FR", 4)]


@dataclass
class Meeting:
    component: str
    section: str
    days: list[str]           # BYDAY codes, e.g. ["MO", "WE"]
    weekday_nums: list[int]
    start: str                # "13:00"
    end: str                  # "14:20"
    room: str
    instructor: str
    date_start: date
    date_end: date


@dataclass
class ScheduledCourse:
    course_id: str
    title: str
    meetings: list[Meeting] = field(default_factory=list)


def _expand_days(s: str) -> tuple[list[str], list[int]]:
    codes: list[str] = []
    nums: list[int] = []
    i = 0
    while i < len(s):
        for tok, code, num in _DAY_TOKENS:
            if s.startswith(tok, i):
                codes.append(code)
                nums.append(num)
                i += len(tok)
                break
        else:
            i += 1
    return codes, nums


def _to_24h(h: str, m: str, ap: str) -> str:
    hour = int(h) % 12 + (12 if ap == "PM" else 0)
    return f"{hour:02d}:{m}"


def parse_class_schedule(text: str) -> dict:
    """-> {"term": "Spring 2026" | None, "courses": [ScheduledCourse, ...]}"""

    lines = [ln.strip() for ln in text.splitlines()]
    term = None
    for ln in lines:
        m = _TERM_RE.search(ln)
        if m:
            term = f"{m.group(1)} {m.group(2)}"
            break

    courses: list[ScheduledCourse] = []
    current: ScheduledCourse | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        cm = _COURSE_RE.match(ln)
        if cm and not any(w in ln for w in ("Academic Calendar", "Start/End")):
            current = ScheduledCourse(
                course_id=re.sub(r"\s+", " ", cm.group(1)), title=cm.group(2).strip(),
            )
            courses.append(current)
            i += 1
            continue
        # A meeting block starts at a bare class number.
        if current is not None and _CLASSNBR_RE.match(ln) and i + 6 < len(lines):
            section, component = lines[i + 1], lines[i + 2]
            daytime, room, instructor = lines[i + 3], lines[i + 4], lines[i + 5]
            dm = _DATES_RE.match(lines[i + 6])
            if component in _COMPONENTS and dm:
                tm = _TIME_RE.match(daytime)
                if tm:  # "TBA" rows carry no schedulable time — skipped
                    codes, nums = _expand_days(tm.group(1))
                    current.meetings.append(Meeting(
                        component=component, section=section,
                        days=codes, weekday_nums=nums,
                        start=_to_24h(tm.group(2), tm.group(3), tm.group(4)),
                        end=_to_24h(tm.group(5), tm.group(6), tm.group(7)),
                        room=room, instructor=instructor,
                        date_start=datetime.strptime(dm.group(1), "%m/%d/%Y").date(),
                        date_end=datetime.strptime(dm.group(2), "%m/%d/%Y").date(),
                    ))
                i += 7
                continue
        i += 1
    return {"term": term, "courses": [c for c in courses if c.meetings or c.title]}


_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Toronto
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def _easter(year: int) -> date:
    """Anonymous Gregorian computus — deterministic, no dependency."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lo = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lo) // 451
    month = (h + lo - 7 * m + 114) // 31
    day = ((h + lo - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _holidays(years: set[int]) -> set[date]:
    """Ontario statutory / UW-closure holidays — no classes meet on these.

    Public, rule-defined dates (nothing invented): Family Day, Good Friday,
    Victoria Day, Canada Day, Civic Holiday, Labour Day, Thanksgiving.
    """

    out: set[date] = set()
    for y in years:
        out.add(_nth_weekday(y, 2, 0, 3))                     # Family Day
        out.add(_easter(y) - timedelta(days=2))               # Good Friday
        vic = date(y, 5, 24)                                  # Victoria Day:
        out.add(vic - timedelta(days=vic.weekday()))          # last Monday ≤ May 24
        out.add(date(y, 7, 1))                                # Canada Day
        out.add(_nth_weekday(y, 8, 0, 1))                     # Civic Holiday
        out.add(_nth_weekday(y, 9, 0, 1))                     # Labour Day
        out.add(_nth_weekday(y, 10, 0, 2))                    # Thanksgiving
    return out


def _first_on_or_after(start: date, weekday_nums: list[int]) -> date | None:
    for off in range(14):
        d = start + timedelta(days=off)
        if d.weekday() in weekday_nums:
            return d
    return None


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def to_ics(parsed: dict) -> str:
    """Weekly-recurring VEVENTs; LOCATION is the real room from the paste."""

    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Schedugoose//Class Schedule//EN",
        f"X-WR-CALNAME:UW {parsed.get('term') or 'Class Schedule'}",
        _VTIMEZONE,
    ]
    n = 0
    years = {c.meetings[0].date_start.year for c in parsed["courses"] if c.meetings}
    years |= {c.meetings[0].date_end.year for c in parsed["courses"] if c.meetings}
    holidays = _holidays(years)
    for course in parsed["courses"]:
        for mt in course.meetings:
            first = _first_on_or_after(mt.date_start, mt.weekday_nums)
            if first is None:
                continue
            n += 1
            start_dt = f"{first:%Y%m%d}T{mt.start.replace(':', '')}00"
            end_dt = f"{first:%Y%m%d}T{mt.end.replace(':', '')}00"
            until = f"{mt.date_end:%Y%m%d}T235959Z"
            # No classes on statutory holidays — exclude the occurrences that
            # would otherwise land on them.
            exdates = sorted(
                d for d in holidays
                if mt.date_start <= d <= mt.date_end and d.weekday() in mt.weekday_nums
            )
            summary = f"{course.course_id} {mt.component}"
            desc = f"{course.title} — {mt.component} {mt.section}"
            if mt.instructor:
                desc += f" — {mt.instructor}"
            out += [
                "BEGIN:VEVENT",
                f"UID:schedugoose-{n}-{first:%Y%m%d}-{mt.start.replace(':', '')}@uwaterloo",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID=America/Toronto:{start_dt}",
                f"DTEND;TZID=America/Toronto:{end_dt}",
                f"RRULE:FREQ=WEEKLY;BYDAY={','.join(mt.days)};UNTIL={until}",
                *([
                    "EXDATE;TZID=America/Toronto:" + ",".join(
                        f"{d:%Y%m%d}T{mt.start.replace(':', '')}00" for d in exdates
                    )
                ] if exdates else []),
                f"SUMMARY:{_ics_escape(summary)}",
                f"LOCATION:{_ics_escape(mt.room)}",
                f"DESCRIPTION:{_ics_escape(desc)}",
                "END:VEVENT",
            ]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
