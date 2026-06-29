"""Academic sequences (co-op streams) by faculty + program identification.

Different faculties run different term sequences:

* **Engineering** is lockstep co-op -- Stream 4 vs Stream 8 differ in when the
  first work term falls.
* **Math** (incl. Computer Science) and **Science** offer a Regular (non-co-op)
  sequence and a Co-op sequence.

A *sequence* is an ordered list of term slots (study or work) with a season.
Seasons are computed by advancing a calendar pointer from a Fall 1A start
(the usual UW start), so only the program/stream needs to be known.

These sequences are representative/simplified versions of the official UW
calendars -- enough to drive term-by-term planning, not a registrar source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Academic calendar order at UW.
_SEASON_ORDER = ["Fall", "Winter", "Spring"]


@dataclass(frozen=True)
class TermSlot:
    label: str        # "1A", "2B", "WT1"
    kind: str         # "study" | "work"
    season: str       # "Fall" | "Winter" | "Spring"
    year_offset: int  # calendar years since the start (Fall) year


@dataclass(frozen=True)
class Sequence:
    key: str
    name: str
    faculty: str
    coop: bool
    slots: tuple[TermSlot, ...]

    def study_terms(self) -> list[TermSlot]:
        return [s for s in self.slots if s.kind == "study"]

    def work_terms(self) -> list[TermSlot]:
        return [s for s in self.slots if s.kind == "work"]


# --------------------------------------------------------------------------- #
# Sequence construction
# --------------------------------------------------------------------------- #
def _build(key: str, name: str, faculty: str, coop: bool, pattern: list[str]) -> Sequence:
    """Build a sequence from a calendar ``pattern`` of slot kinds.

    ``pattern`` entries are "study", "work", or "off", read off consecutive
    calendar terms starting at Fall (1A). Seasons/years are auto-assigned.
    """

    season_idx = 0          # 0=Fall, 1=Winter, 2=Spring
    year_offset = 0
    study_n = 0
    work_n = 0
    slots: list[TermSlot] = []
    for i, kind in enumerate(pattern):
        season = _SEASON_ORDER[season_idx]
        if kind == "study":
            study_n += 1
            year = (study_n + 1) // 2     # 1,1,2,2,3,3,4,4 -> "1A","1B",...
            ab = "A" if study_n % 2 == 1 else "B"
            slots.append(TermSlot(f"{year}{ab}", "study", season, year_offset))
        elif kind == "work":
            work_n += 1
            slots.append(TermSlot(f"WT{work_n}", "work", season, year_offset))
        # advance calendar pointer
        season_idx = (season_idx + 1) % 3
        if season_idx == 1:               # just entered Winter -> new calendar year
            year_offset += 1
    return Sequence(key, name, faculty, coop, tuple(slots))


# Representative sequences (study=S, work=W, off=skip-summer).
SEQUENCES: dict[str, Sequence] = {
    # --- Math / Computer Science ---
    "math-regular": _build(
        "math-regular", "CS Regular (no co-op)", "Math", False,
        ["study", "study", "off"] * 4,
    ),
    "math-coop": _build(
        "math-coop", "CS Co-op", "Math", True,
        ["study", "study", "work",
         "study", "work", "study",
         "work", "study", "work",
         "study", "work", "study",
         "work", "study"],
    ),
    # --- Engineering (lockstep co-op) ---
    "eng-stream8": _build(
        "eng-stream8", "Engineering Stream 8 (first work term after 2A)", "Engineering", True,
        ["study", "study", "off",
         "study", "work", "study",
         "work", "study", "work",
         "study", "work", "study",
         "work", "study"],
    ),
    "eng-stream4": _build(
        "eng-stream4", "Engineering Stream 4 (first work term after 1B)", "Engineering", True,
        ["study", "study", "work",
         "study", "work", "study",
         "work", "study", "work",
         "study", "work", "study",
         "work", "study"],
    ),
    # --- Science ---
    "sci-regular": _build(
        "sci-regular", "Science Regular (no co-op)", "Science", False,
        ["study", "study", "off"] * 4,
    ),
    "sci-coop": _build(
        "sci-coop", "Science Co-op", "Science", True,
        ["study", "study", "work",
         "study", "work", "study",
         "work", "study", "work",
         "study", "work", "study",
         "work", "study"],
    ),
}

FACULTY_SEQUENCES: dict[str, list[str]] = {
    "Math": ["math-regular", "math-coop"],
    "Engineering": ["eng-stream8", "eng-stream4"],
    "Science": ["sci-regular", "sci-coop"],
}


# --------------------------------------------------------------------------- #
# Program identification (NL -> faculty + program + requirement template)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Program:
    name: str
    faculty: str
    reqs_key: str        # key into data.program_reqs.PROGRAMS
    keywords: tuple[str, ...]


# Explicit program phrases beat generic keyword hits (e.g. "cs student" beats "data").
_PROGRAM_PHRASES: list[tuple[str, str]] = [
    (r"\bcs student\b", "Computer Science"),
    (r"\bcomputer science student\b", "Computer Science"),
    (r"\bfirst-?year cs\b", "Computer Science"),
    (r"\bcs major\b", "Computer Science"),
    (r"\bin cs\b", "Computer Science"),
    (r"\bstudy(?:ing)? computer science\b", "Computer Science"),
    (r"\bdata science major\b", "Data Science"),
    (r"\bdata science program\b", "Data Science"),
    (r"\bin data science\b", "Data Science"),
]


PROGRAMS: list[Program] = [
    Program("Computer Science", "Math", "CS-Major",
            ("computer science", "comp sci", "compsci", "cs")),
    Program("Data Science", "Math", "DataScience-Major",
            ("data science major", "data science program")),
    Program("Statistics", "Math", "DataScience-Major",
            ("statistics", "stats major", "actuarial", "actsci")),
    Program("Software Engineering", "Engineering", "Eng-Generic",
            ("software engineering", "soft eng")),
    Program("Computer Engineering", "Engineering", "Eng-Generic",
            ("computer engineering", "comp eng")),
    Program("Electrical Engineering", "Engineering", "Eng-Generic",
            ("electrical engineering", "electrical", "ece")),
    Program("Mechatronics Engineering", "Engineering", "Eng-Generic",
            ("mechatronics engineering", "mechatronics", "mechatronic")),
    Program("Mechanical Engineering", "Engineering", "Eng-Generic",
            ("mechanical engineering", "mechanical", "mech eng")),
    Program("Systems Design Engineering", "Engineering", "Eng-Generic",
            ("systems design engineering", "systems design", "syde")),
    Program("Engineering (general)", "Engineering", "Eng-Generic",
            ("engineering", "engineer")),
    Program("Mathematics", "Math", "CS-Major",
            ("mathematics major", "combinatorics", "pure math", "applied math")),
    Program("Science (general)", "Science", "Science-Generic",
            ("biology", "physics", "chemistry", "life science")),
]


def identify_program(text: str) -> Program | None:
    """Best-effort program identification from free text (word-boundary match).

    Career goals ("data field", "want to do ML") do **not** select a major --
    only explicit program phrases or major-specific keywords do.
    """

    low = text.lower()
    for pattern, name in _PROGRAM_PHRASES:
        if re.search(pattern, low):
            return next(p for p in PROGRAMS if p.name == name)

    best: tuple[int, Program] | None = None
    for prog in PROGRAMS:
        for kw in prog.keywords:
            if re.search(rf"\b{re.escape(kw)}\b", low):
                score = len(kw)
                if best is None or score > best[0]:
                    best = (score, prog)
                break
    return best[1] if best else None


def get_sequence(key: str | None) -> Sequence | None:
    return SEQUENCES.get(key) if key else None


def sequences_for_faculty(faculty: str) -> list[Sequence]:
    return [SEQUENCES[k] for k in FACULTY_SEQUENCES.get(faculty, [])]


def match_sequence(text: str, faculty: str) -> str | None:
    """Map free text to a sequence key within the given faculty."""

    low = text.lower()
    options = FACULTY_SEQUENCES.get(faculty, [])
    if faculty == "Engineering":
        if "stream 4" in low or "stream4" in low or "4 stream" in low:
            return "eng-stream4"
        if "stream 8" in low or "stream8" in low or "8 stream" in low:
            return "eng-stream8"
    if any(k in low for k in ["regular", "non-co", "non co", "no co-op", "no coop", "not co-op"]):
        reg = [k for k in options if "regular" in k]
        if reg:
            return reg[0]
    if any(k in low for k in ["co-op", "coop", "co op"]):
        co = [k for k in options if "coop" in k or "stream" in k]
        if co:
            return co[0]
    return None


# --------------------------------------------------------------------------- #
# Start-term parsing
# --------------------------------------------------------------------------- #
_SEASON_WORDS = {
    "fall": "Fall", "f": "Fall", "autumn": "Fall",
    "winter": "Winter", "w": "Winter",
    "spring": "Spring", "summer": "Spring", "s": "Spring",
}


def parse_start_term(text: str) -> dict | None:
    """Parse a start term like 'Fall 2026', '26 fall', 'f26', '2026 fall'."""

    low = text.lower()
    season = None
    for word, canon in (("fall", "Fall"), ("autumn", "Fall"), ("winter", "Winter"),
                        ("spring", "Spring"), ("summer", "Spring")):
        if word in low:
            season = canon
            break
    # year: 4-digit or 2-digit
    m = re.search(r"\b(20\d{2})\b", low)
    year = int(m.group(1)) if m else None
    if year is None:
        m2 = re.search(r"\b(\d{2})\s*(?:fall|winter|spring|f|w|s)\b|\b(?:fall|winter|spring|f|w|s)\s*(\d{2})\b", low)
        if m2:
            yy = m2.group(1) or m2.group(2)
            year = 2000 + int(yy)
    # short forms like f26 / w27 / s26
    if season is None or year is None:
        m3 = re.search(r"\b([fws])\s?(\d{2})\b", low)
        if m3:
            season = season or _SEASON_WORDS.get(m3.group(1))
            year = year or (2000 + int(m3.group(2)))
    if season and year:
        return {"season": season, "year": year}
    return None


def format_term(term: dict) -> str:
    return f"{term['season']} {term['year']}"


# Calendar-adjacency order *within a calendar year*: Winter→Spring→Fall. (A Fall
# term precedes the following calendar year's Winter, so it sorts last here.)
_CAL_POS = {"Winter": 0, "Spring": 1, "Fall": 2}
_CAL_SEASON = ["Winter", "Spring", "Fall"]


def _abs_term(season: str, year: int) -> int:
    """Absolute term index so consecutive terms differ by exactly 1."""

    return year * 3 + _CAL_POS[season]


def resolve_term(start: dict, year_offset: int, season: str) -> dict:
    """Resolve a slot's real (season, year), honoring the student's start season.

    Sequences are built assuming a Fall 1A start, so each slot carries a
    Fall-anchored ``(season, year_offset)``. We measure how many terms the slot
    sits after 1A, then advance that many terms from the *actual* start term —
    so a "Winter 2027" start shifts the whole sequence (1A → Winter 2027), not
    just renames the year.
    """

    terms_after_1a = _abs_term(season, year_offset) - _abs_term("Fall", 0)
    actual = _abs_term(start.get("season", "Fall"), start["year"]) + terms_after_1a
    return {"season": _CAL_SEASON[actual % 3], "year": actual // 3}
