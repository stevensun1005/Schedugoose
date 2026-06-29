"""Bundled mock course data.

Used when ``UW_API_KEY`` is unset so the whole system runs offline. Rows use a
simplified, normalized shape (``RawRow``) that the real UW API path also feeds
into via :func:`data.uw_api.normalize_rows`.

The catalog spans a 1A->4B Computer Science (Math faculty) progression with
prerequisite chains and degree-requirement category tags, so a first-year can
be planned term by term as prerequisites unlock. It's treated as offered every
study term.
"""

from __future__ import annotations

from typing import TypedDict


class RawMeeting(TypedDict):
    weekdays: str
    start: str   # "HH:MM"
    end: str     # "HH:MM"


class RawRow(TypedDict, total=False):
    course_id: str
    title: str
    units: float
    prereqs: list[str]
    categories: list[str]
    component: str          # LEC | TUT | LAB
    section_code: str
    instructor: str
    term: str
    cap: int
    enrolled: int
    meetings: list[RawMeeting]
    easiness: float
    prof_rating: float


# Pool of distinct lecture time slots, chosen so courses likely co-scheduled in
# one term can be assigned non-overlapping times.
_SLOTS: list[tuple[str, str, str]] = [
    ("MWF", "08:30", "09:20"),   # 0
    ("MWF", "09:30", "10:20"),   # 1
    ("MWF", "10:30", "11:20"),   # 2
    ("MWF", "11:30", "12:20"),   # 3
    ("MWF", "13:30", "14:20"),   # 4
    ("MWF", "14:30", "15:20"),   # 5
    ("TTh", "08:30", "09:50"),   # 6
    ("TTh", "10:00", "11:20"),   # 7
    ("TTh", "11:30", "12:50"),   # 8
    ("TTh", "13:00", "14:20"),   # 9
    ("TTh", "14:30", "15:50"),   # 10
    ("TTh", "16:00", "17:20"),   # 11
]


def _one(
    course_id: str,
    title: str,
    slot: int,
    *,
    prereqs: list[str] | None = None,
    categories: list[str] | None = None,
    easiness: float = 0.5,
    prof_rating: float = 0.6,
    instructor: str = "Staff",
    units: float = 0.5,
) -> RawRow:
    days, start, end = _SLOTS[slot % len(_SLOTS)]
    return RawRow(
        course_id=course_id,
        title=title,
        units=units,
        prereqs=prereqs or [],
        categories=categories or [],
        component="LEC",
        section_code="LEC 001",
        instructor=instructor,
        term="ANY",
        cap=120,
        enrolled=0,
        meetings=[RawMeeting(weekdays=days, start=start, end=end)],
        easiness=easiness,
        prof_rating=prof_rating,
    )


MOCK_ROWS: list[RawRow] = [
    # ---------------- 1A (no prereqs) ----------------
    _one("CS 135", "Designing Functional Programs", 0, categories=["CS-Core", "CS-1xx"], easiness=0.55),
    _one("MATH 135", "Algebra for Honours Math", 1, categories=["Math-Core", "MATH-1xx"], easiness=0.45),
    _one("MATH 137", "Calculus 1 for Honours Math", 7, categories=["Math-Core", "MATH-1xx"], easiness=0.4),
    _one("ENGL 119", "Communications in Math & CS", 9, categories=["Comm", "Elective"], easiness=0.85),
    _one("PD 1", "Career Fundamentals", 5, categories=["Elective", "PD"], easiness=0.9),

    # ---------------- 1B (need 1A) ----------------
    _one("CS 136", "Elementary Algorithm Design", 2, prereqs=["CS 135"], categories=["CS-Core", "CS-1xx"], easiness=0.45),
    _one("MATH 136", "Linear Algebra 1", 3, prereqs=["MATH 135"], categories=["Math-Core", "MATH-1xx"], easiness=0.45),
    _one("MATH 138", "Calculus 2 for Honours Math", 8, prereqs=["MATH 137"], categories=["Math-Core", "MATH-1xx"], easiness=0.4),
    _one("SPCOM 223", "Public Speaking", 10, categories=["Comm", "Elective"], easiness=0.8),
    _one("ECON 101", "Microeconomics", 4, categories=["Elective"], easiness=0.8),

    # ---------------- 2A (need 1B) ----------------
    _one("CS 246", "Object-Oriented Software Development", 0, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx"], easiness=0.5),
    _one("CS 245", "Logic and Computation", 2, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx", "CS-Theory"], easiness=0.5),
    _one("MATH 239", "Introduction to Combinatorics", 8, prereqs=["MATH 136"], categories=["Math-Core", "MATH-2xx"], easiness=0.45),
    _one("STAT 230", "Probability", 4, prereqs=["MATH 138"], categories=["Math-Core", "STAT-Core", "STAT-2xx"], easiness=0.5),
    _one("PHIL 145", "Critical Thinking", 5, categories=["Elective"], easiness=0.85),

    # ---------------- 2B (need 2A) ----------------
    _one("CS 240", "Data Structures and Data Management", 7, prereqs=["CS 136"], categories=["CS-Core", "CS-2xx"], easiness=0.4),
    _one("CS 241", "Foundations of Sequential Programs", 3, prereqs=["CS 246"], categories=["CS-Core", "CS-2xx"], easiness=0.45),
    _one("STAT 231", "Statistics", 9, prereqs=["STAT 230"], categories=["STAT-Core", "STAT-2xx"], easiness=0.45),
    _one("STAT 206", "Statistics for Software Engineering", 11, prereqs=["MATH 239"], categories=["STAT-Core", "STAT-2xx"], easiness=0.5),
    _one("PSYCH 101", "Introduction to Psychology", 5, categories=["Elective"], easiness=0.85),

    # ---------------- 3A (need 2B) ----------------
    _one("CS 341", "Algorithms", 6, prereqs=["CS 240"], categories=["CS-3xx", "CS-Theory"], easiness=0.3,
         instructor="Armin Jamshidpey", prof_rating=0.6),
    _one("CS 350", "Operating Systems", 2, prereqs=["CS 241", "CS 246"], categories=["CS-3xx", "CS-Systems"], easiness=0.4),
    _one("CS 348", "Introduction to Database Management", 1, prereqs=["CS 240"], categories=["CS-3xx", "CS-Systems"], easiness=0.55,
         instructor="Grant Weddell", prof_rating=0.7),
    _one("STAT 341", "Computational Statistics & Data Analysis", 3, prereqs=["STAT 231"], categories=["STAT-ML", "STAT-3xx"], easiness=0.5,
         instructor="Reza Ramezan", prof_rating=0.7),

    # ---------------- 3B (need 3A) ----------------
    _one("CS 360", "Introduction to the Theory of Computing", 8, prereqs=["CS 245", "CS 240"], categories=["CS-3xx", "CS-Theory"], easiness=0.4),
    _one("CS 370", "Numerical Computation", 4, prereqs=["MATH 138", "CS 136"], categories=["CS-3xx"], easiness=0.45),
    _one("CS 442", "Principles of Programming Languages", 9, prereqs=["CS 241"], categories=["CS-4xx"], easiness=0.4),
    _one("CS 466", "Algorithm Design and Analysis", 10, prereqs=["CS 341"], categories=["CS-4xx", "CS-Theory"], easiness=0.35),

    # ---------------- 4A / 4B (need senior prereqs) ----------------
    _one("CS 486", "Introduction to Artificial Intelligence", 9, prereqs=["CS 245", "STAT 231"],
         categories=["CS-AI", "CS-4xx"], easiness=0.45, instructor="Pascal Poupart", prof_rating=0.8),
    _one("CS 480", "Introduction to Machine Learning", 13 % 12, prereqs=["CS 341", "STAT 230"],
         categories=["CS-AI", "STAT-ML", "CS-4xx"], easiness=0.4, instructor="Yaoliang Yu", prof_rating=0.75),
    _one("CS 451", "Data-Intensive Distributed Computing", 7, prereqs=["CS 348"],
         categories=["CS-Systems", "STAT-ML", "CS-4xx"], easiness=0.5, instructor="Ali Mashtizadeh", prof_rating=0.65),
    _one("CO 487", "Applied Cryptography", 5, prereqs=["MATH 135"],
         categories=["CS-Security", "CS-4xx"], easiness=0.4, instructor="David Jao", prof_rating=0.7),
    _one("CS 492", "The Social Implications of Computing", 11, prereqs=[],
         categories=["CS-4xx", "Elective"], easiness=0.85, instructor="Staff", prof_rating=0.7),
]

# CS 486 needs a tutorial too (kept to exercise multi-component linking).
MOCK_ROWS.append(
    RawRow(
        course_id="CS 486", title="Introduction to Artificial Intelligence", units=0.5,
        prereqs=["CS 245", "STAT 231"], categories=["CS-AI", "CS-4xx"],
        component="TUT", section_code="TUT 101", instructor="", term="ANY",
        cap=120, enrolled=0,
        meetings=[RawMeeting(weekdays="W", start="15:30", end="16:20")],
        easiness=0.45, prof_rating=0.8,
    )
)
