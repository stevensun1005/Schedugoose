"""Bundled mock course data (offline catalog).

Spans CS Honours 1A->4B with prerequisite chains, level tags, and electives.
PD courses exist for co-op work terms only (0 degree credit).
"""

from __future__ import annotations

from typing import TypedDict


class RawMeeting(TypedDict):
    weekdays: str
    start: str
    end: str


class RawRow(TypedDict, total=False):
    course_id: str
    title: str
    units: float
    prereqs: list[str]
    categories: list[str]
    component: str
    section_code: str
    instructor: str
    term: str
    cap: int
    enrolled: int
    meetings: list[RawMeeting]
    easiness: float
    prof_rating: float


_SLOTS: list[tuple[str, str, str]] = [
    ("MWF", "08:30", "09:20"), ("MWF", "09:30", "10:20"), ("MWF", "10:30", "11:20"),
    ("MWF", "11:30", "12:20"), ("MWF", "13:30", "14:20"), ("MWF", "14:30", "15:20"),
    ("TTh", "08:30", "09:50"), ("TTh", "10:00", "11:20"), ("TTh", "11:30", "12:50"),
    ("TTh", "13:00", "14:20"), ("TTh", "14:30", "15:50"), ("TTh", "16:00", "17:20"),
    ("MW", "13:00", "14:20"), ("MW", "15:00", "16:20"), ("F", "10:00", "12:00"),
]


def _one(
    course_id: str, title: str, slot: int, *,
    prereqs: list[str] | None = None,
    categories: list[str] | None = None,
    easiness: float = 0.5,
    prof_rating: float = 0.6,
    instructor: str = "Staff",
    units: float = 0.5,
) -> RawRow:
    days, start, end = _SLOTS[slot % len(_SLOTS)]
    return RawRow(
        course_id=course_id, title=title, units=units,
        prereqs=prereqs or [], categories=categories or [],
        component="LEC", section_code="LEC 001", instructor=instructor,
        term="ANY", cap=120, enrolled=0,
        meetings=[RawMeeting(weekdays=days, start=start, end=end)],
        easiness=easiness, prof_rating=prof_rating,
    )


MOCK_ROWS: list[RawRow] = [
    # ---- 1A ----
    _one("CS 135", "Designing Functional Programs", 0, categories=["CS-Core", "CS-1xx"]),
    _one("MATH 135", "Algebra for Honours Math", 1, categories=["Math-Core", "MATH-1xx"], easiness=0.45),
    _one("MATH 137", "Calculus 1 for Honours Math", 7, categories=["Math-Core", "MATH-1xx"], easiness=0.4),
    _one("ENGL 119", "Communications in Math & CS", 9, categories=["Comm", "Elective"], easiness=0.85),
    _one("ANTH 100", "Introduction to Anthropology", 11, categories=["Elective"], easiness=0.88),
    _one("GEOG 101", "Introduction to Physical Geography", 12, categories=["Elective"], easiness=0.82),
    _one("FREN 101", "Introduction to French Language 1", 13, categories=["Language", "Elective"], easiness=0.75),
    _one("GER 101", "Elementary German 1", 14, categories=["Language", "Elective"], easiness=0.75),
    _one("SPAN 101", "Introduction to Spanish 1", 15, categories=["Language", "Elective"], easiness=0.75),
    _one("ENGL 129", "Written Academic English", 4, categories=["Intl-English", "Comm", "Elective"], easiness=0.78),
    _one("ELL 102", "English Language Learning 2", 6, categories=["Intl-English", "Elective"], easiness=0.8),

    # ---- 1B ----
    _one("CS 136", "Elementary Algorithm Design", 2, prereqs=["CS 135"], categories=["CS-Core", "CS-1xx"]),
    _one("MATH 136", "Linear Algebra 1", 3, prereqs=["MATH 135"], categories=["Math-Core", "MATH-1xx"]),
    _one("MATH 138", "Calculus 2 for Honours Math", 8, prereqs=["MATH 137"], categories=["Math-Core", "MATH-1xx"]),
    _one("SPCOM 223", "Public Speaking", 10, categories=["Comm", "Elective"], easiness=0.8),
    _one("ECON 101", "Microeconomics", 4, categories=["Elective"], easiness=0.8),
    _one("MUSIC 116", "Music and Culture", 13, categories=["Elective"], easiness=0.9),

    # ---- 2A ----
    _one("CS 246", "Object-Oriented Software Development", 0, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx"]),
    _one("CS 245", "Logic and Computation", 2, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx", "CS-Theory"]),
    _one("MATH 239", "Introduction to Combinatorics", 8, prereqs=["MATH 136"], categories=["Math-Core", "MATH-2xx"]),
    _one("MATH 237", "Calculus 3 for Honours Math", 6, prereqs=["MATH 138"], categories=["Math-Core", "MATH-2xx"]),
    _one("STAT 230", "Probability", 4, prereqs=["MATH 138"], categories=["Math-Core", "STAT-Core", "STAT-2xx"]),
    _one("PHIL 145", "Critical Thinking", 5, categories=["Elective"], easiness=0.85),
    _one("RS 110", "Religions of the West", 14, categories=["Elective"], easiness=0.86),

    # ---- 2B ----
    _one("CS 240", "Data Structures and Data Management", 7, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx"]),
    _one("CS 241", "Foundations of Sequential Programs", 3, prereqs=["CS 246"], categories=["CS-Core", "CS-2xx"]),
    _one("STAT 231", "Statistics", 9, prereqs=["STAT 230"], categories=["STAT-Core", "STAT-2xx"]),
    _one("STAT 206", "Statistics for Software Engineering", 11, prereqs=["MATH 239"], categories=["STAT-Core", "STAT-2xx"]),
    _one("PSYCH 101", "Introduction to Psychology", 5, categories=["Elective"], easiness=0.85),
    _one("ARTS 130", "Introduction to Digital Media", 15, categories=["Elective"], easiness=0.84),

    # ---- 3A ----
    _one("CS 341", "Algorithms", 6, prereqs=["CS 240"], categories=["CS-3xx", "CS-Theory"], easiness=0.3),
    _one("CS 350", "Operating Systems", 2, prereqs=["CS 241", "CS 246"], categories=["CS-3xx", "CS-Systems"]),
    _one("CS 348", "Introduction to Database Management", 1, prereqs=["CS 240"], categories=["CS-3xx", "CS-Systems"]),
    _one("STAT 341", "Computational Statistics & Data Analysis", 3, prereqs=["STAT 231"], categories=["STAT-ML", "STAT-3xx"]),
    _one("CS 343", "Parallel and Concurrent Programming", 12, prereqs=["CS 241"], categories=["CS-3xx", "CS-Systems"]),
    _one("EARTH 121", "Introductory Earth Sciences", 13, categories=["Elective"], easiness=0.83),

    # ---- 3B ----
    _one("CS 360", "Introduction to the Theory of Computing", 8, prereqs=["CS 245", "CS 240"], categories=["CS-3xx", "CS-Theory"]),
    _one("CS 370", "Numerical Computation", 4, prereqs=["MATH 138", "CS 136"], categories=["CS-3xx"]),
    _one("CS 442", "Principles of Programming Languages", 9, prereqs=["CS 241"], categories=["CS-4xx"]),
    _one("CS 466", "Algorithm Design and Analysis", 10, prereqs=["CS 341"], categories=["CS-4xx", "CS-Theory"]),
    _one("CS 446", "Software Design and Architecture", 14, prereqs=["CS 246", "CS 348"], categories=["CS-4xx", "CS-Systems"]),
    _one("SOC 101", "Introduction to Sociology", 5, categories=["Elective"], easiness=0.87),

    # ---- 4A / 4B (data / AI track) ----
    _one("CS 486", "Introduction to Artificial Intelligence", 9, prereqs=["CS 245", "STAT 231"],
         categories=["CS-AI", "CS-4xx"], easiness=0.45, instructor="Pascal Poupart", prof_rating=0.8),
    _one("CS 480", "Introduction to Machine Learning", 7, prereqs=["CS 341", "STAT 230"],
         categories=["CS-AI", "STAT-ML", "CS-4xx"], easiness=0.4, instructor="Yaoliang Yu"),
    _one("CS 451", "Data-Intensive Distributed Computing", 12, prereqs=["CS 348"],
         categories=["CS-Systems", "STAT-ML", "CS-4xx"], instructor="Ali Mashtizadeh"),
    _one("CS 479", "Neural Networks", 13, prereqs=["CS 480"], categories=["CS-AI", "CS-4xx"]),
    _one("CS 492", "The Social Implications of Computing", 11,
         prereqs=["CS 246", "CS 240"], categories=["CS-4xx", "Elective"], easiness=0.85),
    _one("CO 487", "Applied Cryptography", 5, prereqs=["MATH 135"], categories=["CS-Security", "CS-4xx"]),
    _one("CS 484", "Computational Vision", 14, prereqs=["CS 480"], categories=["CS-AI", "CS-4xx"]),
    _one("CS 497", "Independent Study", 15, prereqs=["CS 341"], categories=["CS-4xx", "Elective"], easiness=0.7),
    _one("CS 454", "Distributed Systems", 0, prereqs=["CS 350", "CS 348"], categories=["CS-4xx", "CS-Systems"]),
    _one("CS 459", "Privacy, Cryptography, Security", 1, prereqs=["CS 350"], categories=["CS-4xx", "CS-Security"]),
    _one("STAT 332", "Applied Linear Models", 2, prereqs=["STAT 231"], categories=["STAT-Core", "STAT-3xx"]),
    _one("MATH 235", "Linear Algebra 2", 3, prereqs=["MATH 136"], categories=["Math-Core", "MATH-2xx"]),
    _one("ENGL 210", "Technical Writing", 4, categories=["Comm", "Elective"], easiness=0.82),
]

# CS 486 tutorial
MOCK_ROWS.append(RawRow(
    course_id="CS 486", title="Introduction to Artificial Intelligence", units=0.5,
    prereqs=["CS 245", "STAT 231"], categories=["CS-AI", "CS-4xx"],
    component="TUT", section_code="TUT 101", instructor="", term="ANY", cap=120, enrolled=0,
    meetings=[RawMeeting(weekdays="W", start="15:30", end="16:20")],
    easiness=0.45, prof_rating=0.8,
))

# PD courses: co-op work terms only (units=0, not degree credit)
for n in range(1, 7):
    MOCK_ROWS.append(RawRow(
        course_id=f"PD {n}", title=f"Professional Development {n}", units=0.0,
        prereqs=[], categories=["PD"], component="LEC", section_code="LEC 001",
        instructor="PD Centre", term="ANY", cap=500, enrolled=0,
        meetings=[RawMeeting(weekdays="F", start="12:00", end="13:00")],
        easiness=0.95, prof_rating=0.5,
    ))
