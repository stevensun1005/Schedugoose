"""Parse a Quest (UW) unofficial transcript into completed / failed / in-progress.

A blind course-code sweep over a transcript is wrong in two ways a real
transcript demonstrates immediately:

1. Quest lists FAILED attempts too ("CS 245 ... 0.50 0.00 46"). Counting those
   as completed makes the planner skip a course the student still needs.
2. The final enrolled term has no grades yet — those are in progress, not done.

So we parse the "Attempted Earned Grade" columns: earned > 0 -> completed,
earned 0.00 -> failed, no numbers -> in progress. Document order means a retake
overrides an earlier failure (CS 136 failed W23, passed S23 -> completed), while
a course failed on every attempt stays failed.
"""

from __future__ import annotations

import re
from typing import TypedDict

# "CS  135", "ACTSC  221", "BUS  111W", "MTHEL   99" — Quest pads with 1-4
# spaces; subjects run 2-6 letters; WLU cross-listed codes carry a W suffix.
# (?![\d.]) keeps "GPA 69.20" / "Totals 2.50" from matching.
_ENTRY_RE = re.compile(r"\b([A-Z]{2,6})\s{1,4}(\d{2,3}[A-Z]?)(?![\d.])\b")
# "0.50 0.50 73" -> (attempted, earned, grade); grade may be a number, letter,
# or CR/NCR. The pair can wrap onto the next line (long titles).
_PAIR_RE = re.compile(r"(\d+\.\d{2})\s+(\d+\.\d{2})\s*(\S{1,3})?")
_PROGRAM_RE = re.compile(r"Program:\s*(.+)")
_LEVEL_RE = re.compile(r"Level:\s*(\d[AB])")
_TERM_RE = re.compile(r"\b(Fall|Winter|Spring)\s+(20\d\d)\b")
# "Cumulative Totals 20.50 17.25" -> (attempted, earned)
_CUM_RE = re.compile(r"Cumulative Totals\s+([\d.]+)\s+([\d.]+)")
_NON_SUBJECTS = {"GPA", "ID", "NBR"}

_NEXT_SEASON = {"Winter": ("Spring", 0), "Spring": ("Fall", 0), "Fall": ("Winter", 1)}


class TranscriptInfo(TypedDict):
    completed: list[str]
    failed: list[str]
    in_progress: list[str]
    program: str | None
    level: str | None
    last_term: dict | None      # the most recent enrolled term, e.g. Spring 2026
    next_term: dict | None      # the term after it — where planning starts
    coop: bool
    units_earned: float | None  # cumulative earned + in-progress attempted


def looks_like_transcript(text: str) -> bool:
    return (
        "Unofficial Transcript" in text
        or text.count("Attempted Earned Grade") >= 1
    )


def parse_transcript(text: str) -> TranscriptInfo:
    entries = list(_ENTRY_RE.finditer(text))
    state: dict[str, str] = {}
    order: list[str] = []

    for i, m in enumerate(entries):
        subj, num = m.group(1), m.group(2)
        if subj in _NON_SUBJECTS:
            continue
        code = f"{subj} {num}"
        # Look for this course's Attempted/Earned pair before the next code.
        window_end = entries[i + 1].start() if i + 1 < len(entries) else len(text)
        window = text[m.end(): min(window_end, m.end() + 160)]
        pair = _PAIR_RE.search(window)
        if code not in order:
            order.append(code)
        if pair:
            earned = float(pair.group(2))
            grade = (pair.group(3) or "").upper()
            # CR with 0.00 earned is a 0-credit milestone (e.g. MTHEL 99), not a fail.
            done = earned > 0 or grade == "CR"
            state[code] = "completed" if done else "failed"  # last attempt wins
        else:
            # A row with no numbers: either the in-progress final term, or a
            # prose mention ("Credit for CS 136 suppressed..."). Prose must not
            # override a real graded row, so only set state for unseen codes.
            state.setdefault(code, "in_progress")

    out: TranscriptInfo = {
        "completed": [c for c in order if state.get(c) == "completed"],
        "failed": [c for c in order if state.get(c) == "failed"],
        "in_progress": [c for c in order if state.get(c) == "in_progress"],
        "program": None,
        "level": None,
        "last_term": None,
        "next_term": None,
        "coop": False,
        "units_earned": None,
    }
    programs = _PROGRAM_RE.findall(text)
    if programs:
        out["program"] = programs[-1].strip()  # last = current program
        out["coop"] = any("co-op" in p.lower() or "co-operative" in p.lower() for p in programs)
    levels = _LEVEL_RE.findall(text)
    if levels:
        out["level"] = levels[-1]

    terms = _TERM_RE.findall(text)
    if terms:
        season, year = terms[-1][0], int(terms[-1][1])
        out["last_term"] = {"season": season, "year": year}
        nxt, bump = _NEXT_SEASON[season]
        out["next_term"] = {"season": nxt, "year": year + bump}

    cums = _CUM_RE.findall(text)
    if cums:
        earned = float(cums[-1][1])
        # In-progress courses have no earned credit yet but will by next term.
        out["units_earned"] = round(earned + 0.5 * len(out["in_progress"]), 2)
    return out
