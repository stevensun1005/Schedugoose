"""Official SCS suggested course sequences (term-by-term charts).

Transcribed from the Cheriton School of Computer Science 2022-2023 suggested-
sequence charts (cs.uwaterloo.ca/suggested-sequences; PDFs scs-2022-2023-*).
Each chart has two streams: students who began with CS 115, and students who
began with CS 135/145 (the standard honours entry). Placeholder tokens
("List I course", "Non-math", "Elective", "CS 3xx/4xx") are the charts' own.

This is presentation/advice data ("when is CS 341 normally taken?"), not
degree requirements — those come live from the calendar (requirements_compiler).
"""

from __future__ import annotations

import re

SOURCE = "cs.uwaterloo.ca/suggested-sequences (SCS 2022-2023 charts)"

LIST_I = ("At least 60% in one of: EMLS 101R, EMLS 102R, EMLS/ENGL 129R, "
          "ENGL 109, SPCOM 100, SPCOM 223.")
LIST_II = ("One of: EMLS 103R, EMLS 104R, EMLS 110R, ENGL 101B, ENGL 108D, "
           "ENGL 119, ENGL 208B, ENGL 209, ENGL 210E, ENGL 210F, ENGL 251A, "
           "SPCOM 225, SPCOM 227, SPCOM 228, or an additional List I course.")

_FY_115 = {
    "1A": ["CS 115", "MATH 135", "MATH 137", "List I course", "Non-math"],
    "1B": ["CS 116", "MATH 136", "MATH 138", "List II course", "Non-math"],
}
_FY_135 = {
    "1A": ["CS 135 or CS 145", "MATH 135", "MATH 137", "List I course", "Non-math"],
    "1B": ["(CS 136 or CS 146) and CS 136L", "MATH 136", "MATH 138", "List II course", "Non-math"],
}

CHARTS: dict[str, dict] = {
    "BCS": {
        "title": "BCS (Bachelor of Computer Science)",
        "cs115": {
            **_FY_115,
            "2A": ["CS 136 and CS 136L", "STAT 230", "Non-math", "Non-math elective"],
            "2B": ["CS 245", "CS 246", "STAT 231", "Non-math", "Non-math"],
            "3A": ["CS 240", "CS 241", "CS 251", "MATH 239", "Non-math"],
            "3B": ["CS 350", "CS 341", "CS 3xx/4xx", "Non-math", "Elective"],
            "4A": ["Courses to complete degree requirements."],
            "4B": ["Courses to complete degree requirements."],
        },
        "cs135": {
            **_FY_135,
            "2A": ["CS 246", "CS 245", "STAT 230", "Non-math", "Non-math"],
            "2B": ["CS 240", "CS 251", "CS 241", "MATH 239", "Non-math"],
            "3A": ["CS 341", "CS 350", "STAT 231", "Non-math", "Elective"],
            "3B": ["CS 3xx/4xx", "CS 3xx/4xx", "Non-math", "Non-math", "Elective"],
            "4A": ["Courses to complete degree requirements."],
            "4B": ["Courses to complete degree requirements."],
        },
        "notes": [],
    },
    "BMath (CS)": {
        "title": "BMath Computer Science",
        "cs115": {
            **_FY_115,
            "2A": ["CS 136 and CS 136L", "CS 245 (advisor consent)", "MATH 235", "MATH 237", "Non-math"],
            "2B": ["CS 246", "CS 251", "MATH 239", "STAT 230", "Non-math"],
            "3A": ["CS 240", "CS 241", "STAT 231", "Non-math", "Elective"],
            "3B": ["CS 350", "CS 341", "CS 370 or CS 371", "Math course (ACTSC/AMATH/CO/PMATH/STAT)", "Non-math"],
            "4A": ["Courses to complete degree requirements."],
            "4B": ["Courses to complete degree requirements."],
        },
        "cs135": {
            **_FY_135,
            "2A": ["CS 246", "CS 245", "MATH 235", "MATH 237", "STAT 230"],
            "2B": ["CS 240", "CS 241", "CS 251", "MATH 239", "Non-math"],
            "3A": ["CS 350", "CS 360 or CS 365", "STAT 231", "Non-math", "Non-math"],
            "3B": ["CS 341", "CS 370 or CS 371", "Math course (ACTSC/AMATH/CO/PMATH/STAT)", "Non-math", "Elective"],
            "4A": ["Courses to complete degree requirements."],
            "4B": ["Courses to complete degree requirements."],
        },
        "notes": [],
    },
    "BCS/SE": {
        "title": "BCS — Software Engineering option",
        "cs115": {
            **_FY_115,
            "2A": ["CS 136 and CS 136L", "CS 245 (advisor consent)", "MATH 239", "STAT 230", "Elective"],
            "2B": ["CS 246", "CS 251", "CS 370 or Non-math", "STAT 231", "Elective"],
            "3A": ["CS 240", "CS 241", "Non-math", "Non-math", "Elective"],
            "3B": ["CS 341", "CS 350", "CS 3xx/4xx", "Non-math", "Elective"],
            "4A": ["CS 446, CS 447, CS 492 (see advisor for timing)"],
            "4B": ["Courses to complete degree requirements."],
        },
        "cs135": {
            **_FY_135,
            "2A": ["CS 246", "CS 245", "MATH 239", "STAT 230", "Elective"],
            "2B": ["CS 240", "CS 241", "CS 251", "STAT 231", "Elective"],
            "3A": ["CS 341", "CS 350", "Non-math", "Non-math", "Elective"],
            "3B": ["CS 445", "CS 3xx/4xx", "Non-math", "Elective", "Elective"],
            "4A": ["CS 446, CS 447, CS 492 (see advisor for timing)"],
            "4B": ["Courses to complete degree requirements."],
        },
        "notes": [],
    },
    "BCS/DH": {
        "title": "BCS — Digital Hardware option",
        "cs115": {
            **_FY_115,
            "2A": ["CS 136 and CS 136L", "CS 245 (advisor consent)", "GENE 123/MTE 120", "STAT 230", "Non-math"],
            "2B": ["CS 246", "ECE 124", "STAT 231", "MATH 239", "Non-math"],
            "3A": ["CS 240", "CS 241", "ECE 222", "Non-math", "Elective"],
            "3B": ["CS 350", "CS 341", "ECE 224/MTE 325", "Non-math", "Elective"],
            "4A": ["Courses to complete degree requirements (ECE 327 in 4A)."],
            "4B": ["Courses to complete degree requirements (ECE 423 + CS 450 or ECE 429)."],
        },
        "cs135": {
            **_FY_135,
            "2A": ["CS 245", "CS 246", "GENE 123/MTE 120", "STAT 230", "Non-math"],
            "2B": ["CS 240", "CS 241", "ECE 124", "MATH 239", "Non-math"],
            "3A": ["CS 341", "CS 350 (advisor consent with ECE 222)", "ECE 222", "STAT 231", "Non-math"],
            "3B": ["CS 3xx/4xx", "CS 3xx/4xx", "ECE 224/MTE 325", "Non-math", "Elective"],
            "4A": ["Courses to complete degree requirements (ECE 327 in 4A)."],
            "4B": ["Courses to complete degree requirements (ECE 423 + CS 450 or ECE 429)."],
        },
        "notes": ["Digital Hardware is only available in co-op sequence 4."],
    },
    "BMath (CS/DH)": {
        "title": "BMath Computer Science — Digital Hardware option",
        "cs115": {
            **_FY_115,
            "2A": ["CS 136 and CS 136L", "CS 245 (advisor consent)", "GENE 123 or MTE 120", "MATH 235", "STAT 230"],
            "2B": ["CS 246", "ECE 124", "MATH 237", "MATH 239", "Non-math"],
            "3A": ["CS 240", "CS 241", "ECE 222", "STAT 231", "Non-math"],
            "3B": ["CS 350", "CS 341", "ECE 224/ECE 325/MTE 325", "Math course (ACTSC/AMATH/CO/PMATH/STAT)", "Elective"],
            "4A": ["Courses to complete degree requirements (ECE 327 in 4A)."],
            "4B": ["Courses to complete degree requirements (ECE 423 + CS 450 or ECE 429)."],
        },
        "cs135": {
            **_FY_135,
            "2A": ["CS 246", "CS 245", "GENE 123 or MTE 120", "MATH 235", "STAT 230"],
            "2B": ["CS 240", "CS 241", "ECE 124", "MATH 237", "MATH 239"],
            "3A": ["CS 360 or CS 365", "CS 350 (advisor consent with ECE 222)", "ECE 222", "STAT 231", "Non-math"],
            "3B": ["CS 341", "CS 370 or CS 371", "ECE 224/ECE 325/MTE 325", "Math course (ACTSC/AMATH/CO/PMATH/STAT)", "Elective"],
            "4A": ["Courses to complete degree requirements (ECE 327 in 4A)."],
            "4B": ["Courses to complete degree requirements (ECE 423 + CS 450 or ECE 429)."],
        },
        "notes": ["Digital Hardware is only available in co-op sequence 4."],
    },
}


def chart_key_for(text: str, program: str | None = None) -> str | None:
    """Pick the chart a question refers to (program + option keywords)."""

    low = f"{text} {program or ''}".lower()
    dh = "digital hardware" in low or "/dh" in low or " dh" in low
    se_opt = "software engineering option" in low or "/se" in low or "se option" in low
    bmath = "bmath" in low or "math faculty" in low or "bachelor of math" in low
    cs = "computer science" in low or "bcs" in low or re.search(r"\bcs\b", low)
    if not (cs or bmath):
        return None
    if dh:
        return "BMath (CS/DH)" if bmath else "BCS/DH"
    if se_opt:
        return "BCS/SE"
    return "BMath (CS)" if bmath else "BCS"


def format_chart(key: str, stream: str = "cs135") -> str | None:
    chart = CHARTS.get(key)
    if not chart:
        return None
    seq = chart.get(stream) or chart["cs135"]
    stream_label = "began with CS 135/145" if stream == "cs135" else "began with CS 115"
    lines = [f"**{chart['title']}** — official suggested sequence ({stream_label}):"]
    for term, courses in seq.items():
        lines.append(f"  - {term}: {', '.join(courses)}")
    for note in chart.get("notes", []):
        lines.append(f"Note: {note}")
    lines.append(f"List I: {LIST_I}")
    lines.append(f"List II: {LIST_II}")
    lines.append(f"Source: {SOURCE}")
    if stream == "cs135":
        lines.append("(There's also a CS 115-start variant — ask if that's you.)")
    return "\n".join(lines)
