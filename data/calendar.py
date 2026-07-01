"""On-demand UW Undergraduate Calendar retrieval — requirements without hardcoding.

UW has hundreds of programs across every faculty; enumerating their requirements
in Python does not scale. Instead we fetch the authoritative UW calendar on
demand and let the RAG layer ground an answer in it.

The stable seam is the per-subject course page, which exists for *every* subject
at a predictable URL:

    https://ucalendar.uwaterloo.ca/<YEAR>/COURSE/course-<SUBJECT>.html

So adding a program means mapping it to its subject code(s) here (data, not
requirement logic) — the actual course text comes from UW at query time.
"""

from __future__ import annotations

import re

import httpx

from data.cache import get_or_set

_BASE = "https://ucalendar.uwaterloo.ca"
_CACHE_TTL = 60 * 60 * 24  # calendar changes rarely
# Calendar years to probe, newest first (e.g. "2526" = 2025-2026).
_YEARS = ("2526", "2425", "2324")

# Program / field → UW subject code(s) whose courses ground its requirements.
# Extend this to support a new program; requirements are never typed here.
PROGRAM_SUBJECTS: dict[str, list[str]] = {
    "computer science": ["CS"],
    "software engineering": ["SE", "ECE", "CS"],
    "data science": ["CS", "STAT"],
    "statistics": ["STAT"],
    "actuarial science": ["ACTSC", "STAT"],
    "combinatorics and optimization": ["CO"],
    "pure mathematics": ["PMATH"],
    "applied mathematics": ["AMATH"],
    "electrical engineering": ["ECE"],
    "computer engineering": ["ECE"],
    "mechatronics engineering": ["MTE"],
    "mechatronics": ["MTE"],
    "mechanical engineering": ["ME"],
    "systems design engineering": ["SYDE"],
    "systems design": ["SYDE"],
    "civil engineering": ["CIVE"],
    "chemical engineering": ["CHE"],
    "management engineering": ["MSCI"],
    "economics": ["ECON"],
    "biology": ["BIOL"],
    "biomedical sciences": ["BIOL", "BME"],
    "chemistry": ["CHEM"],
    "physics": ["PHYS"],
    "psychology": ["PSYCH"],
    "kinesiology": ["KIN"],
    "health sciences": ["HLTH"],
    "accounting": ["AFM"],
    "finance": ["AFM", "ECON"],
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def subjects_for_program(query: str) -> list[str]:
    """Best-effort subject codes for a program mentioned in free text."""

    low = query.lower()
    for name, subjects in PROGRAM_SUBJECTS.items():
        if name in low:
            return subjects
    # bare subject code like "ECE" / "biol"
    m = re.search(r"\b([a-z]{2,6})\b", low)
    if m and m.group(1).upper() in {s for subs in PROGRAM_SUBJECTS.values() for s in subs}:
        return [m.group(1).upper()]
    return []


def _html_to_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#160;", " ")
    text = _WS_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def course_page_url(subject: str, year: str | None = None) -> str:
    return f"{_BASE}/{year or _YEARS[0]}/COURSE/course-{subject.upper()}.html"


def fetch_subject_courses(subject: str) -> tuple[str, str] | None:
    """Fetch a subject's calendar course page as (text, url). Cached; None on failure."""

    def _producer() -> dict[str, str]:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            for year in _YEARS:
                url = course_page_url(subject, year)
                try:
                    resp = client.get(url)
                    if resp.status_code == 200 and resp.text:
                        return {"text": _html_to_text(resp.text), "url": url}
                except Exception:
                    continue
        return {}

    try:
        data = get_or_set(f"cal:courses:{subject.upper()}", _CACHE_TTL, _producer)
    except Exception:
        data = {}
    if data and data.get("text"):
        return data["text"], data["url"]
    return None


def course_blurb(course_id: str) -> tuple[str, str] | None:
    """Extract one course's calendar entry (title + description) as (text, url).

    Works for any subject via the stable per-subject course page, so lookups
    aren't limited to the bundled catalog.
    """

    m = re.match(r"\s*([A-Za-z]{2,6})\s*(\d{3}[A-Za-z]?)", course_id)
    if not m:
        return None
    subject, num = m.group(1).upper(), m.group(2).upper()
    fetched = fetch_subject_courses(subject)
    if not fetched:
        return None
    text, url = fetched
    # Capture from the course code up to the next course code (its full entry).
    pat = re.compile(rf"\b{subject}\s?{num}\b(.*?)(?=\b[A-Z]{{2,6}}\s?\d{{3}}[A-Za-z]?\b|\Z)", re.S)
    hit = pat.search(text)
    if not hit:
        return None
    blurb = re.sub(r"\s+", " ", f"{subject} {num}{hit.group(1)}").strip()
    return (blurb[:600], url) if len(blurb) > len(f"{subject} {num}") + 5 else None


def calendar_link(query: str) -> str:
    """A verify-here link: the subject course page, else the calendar home."""

    subs = subjects_for_program(query)
    if subs:
        return course_page_url(subs[0])
    return f"{_BASE}/"
