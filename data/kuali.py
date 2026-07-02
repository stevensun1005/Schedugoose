"""UW academic-calendar (Kuali) client — authoritative program requirements.

The public calendar at uwaterloo.ca/academic-calendar is a Kuali SPA backed by a
JSON API. This fetches a program's *actual* requirement text ("Complete 1 of:
CS 240 / CS 250 …") on demand, so requirements come from the registrar source
for ANY program — no hardcoding.

    search_programs("computer science") -> [{title, pid, code, ...}]
    requirements_for("mechatronics engineering") -> (requirement_text, catalog_url)
"""

from __future__ import annotations

import re

import httpx

from data.cache import get_or_set

_HOST = "https://uwaterloocm.kuali.co"
_PAGE = "https://uwaterloo.ca/academic-calendar/undergraduate-studies/catalog"
_FALLBACK_CATALOG = "67e557ed6ed2fe2bd3a38956"  # current catalog id (auto-refreshed below)
_CACHE_TTL = 60 * 60 * 24
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_TAG_RE = re.compile(r"<[^>]+>")


def _catalog_id() -> str:
    """Discover the active catalog id from the calendar page (cached)."""

    def _producer() -> dict[str, str]:
        try:
            with httpx.Client(timeout=15.0, headers=_HEADERS, follow_redirects=True) as c:
                html = c.get(_PAGE).text
            m = re.search(r"catalogId\s*=\s*'([a-f0-9]{24})'", html)
            if m:
                return {"id": m.group(1)}
        except Exception:
            pass
        return {"id": _FALLBACK_CATALOG}

    try:
        return get_or_set("kuali:catalog_id", _CACHE_TTL, _producer)["id"]
    except Exception:
        return _FALLBACK_CATALOG


def _get_json(url: str):
    with httpx.Client(timeout=20.0, headers=_HEADERS, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.json()


def search_programs(query: str, limit: int = 60) -> list[dict]:
    cid = _catalog_id()
    key = f"kuali:search:v2:{query.lower()}:{limit}"

    def _producer() -> list[dict]:
        try:
            q = httpx.QueryParams({"q": query})["q"]
            # The API caps its default page well below the match count — a
            # sub-plan like "MS-Business Specialization" only appears with an
            # explicit big limit, so always ask wide and let ranking decide.
            data = _get_json(f"{_HOST}/api/v1/catalog/search/{cid}?q={q}&limit=100")
            return [
                {"title": p.get("title", ""), "pid": p.get("pid", ""), "code": p.get("code", "")}
                for p in data[:limit] if p.get("pid")
            ]
        except Exception:
            return []

    try:
        return get_or_set(key, _CACHE_TTL, _producer)
    except Exception:
        return []


_STOP = {
    "what", "are", "the", "for", "requirement", "requirements", "program", "programs",
    "courses", "course", "need", "do", "i", "to", "get", "an", "of", "in", "tell",
    "me", "about", "which", "does", "require", "and",
}


def _clean_terms(query: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2 and w not in _STOP]


def _search_union(query: str) -> list[dict]:
    """Search the cleaned query plus its strongest individual terms and merge —
    Kuali ranks single strong terms better than multi-word phrases, so a program
    like 'Electrical Engineering' surfaces from the 'electrical' search even when
    the full phrase misses it."""

    terms = _clean_terms(query)
    queries = [" ".join(terms) if terms else query]
    queries += sorted(set(terms), key=len, reverse=True)[:2]  # two strongest terms
    seen: set[str] = set()
    merged: list[dict] = []
    for q in dict.fromkeys(queries):  # dedupe, preserve order
        # Full width: a same-titled sub-plan ("MS-Business Specialization")
        # sits deep in the result list (position ~75 of 100) — our own ranking
        # decides, not the API's ordering.
        for p in search_programs(q, limit=100):
            if p["pid"] not in seen:
                seen.add(p["pid"])
                merged.append(p)
    return merged


_COURSE_CODE = re.compile(r"^[A-Z]{2,6}\s?\d{3}[A-Z]?$")
_CREDENTIALS = ("bachelor", "honours", "minor", "specialization", "option", "major", "diploma")


def _program_initials(program: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z]+", program)).upper()


def _ranked(query: str, results: list[dict], program: str | None = None) -> list[dict]:
    """Programs (not course entries) ranked by relevance to the query.

    ``program`` is the student's own program: sub-plans (specializations,
    minors) exist under many parents with identical titles ("Business
    Specialization" exists for CS, Math Studies, Math Optimization, …) and are
    disambiguated only by the code prefix ("MS-Business Specialization") —
    match it against the program's initials or name.
    """

    low = query.lower()
    want_minor = "minor" in low
    want_spec = "special" in low or "spec" in low
    terms = _clean_terms(query)
    programs = [p for p in results if not _COURSE_CODE.match(p.get("code", "").strip())]
    prog_low = (program or "").lower()
    prog_initials = _program_initials(program) if program else ""

    def score(p: dict) -> tuple:
        t = p["title"].lower()
        code = (p.get("code") or "")
        prefix = code.split("-")[0].strip().upper()
        ctx = 0
        if program:
            if prog_initials and prefix == prog_initials:
                ctx = 1
            elif prog_low and prog_low in t:
                ctx = 1
        overlap = sum(1 for w in terms if w in t)
        is_sub = any(w in t for w in ("option", "specialization", "minor"))
        if want_minor:
            kind = 1 if "minor" in t else 0
        elif want_spec:
            kind = 1 if ("special" in t or "option" in t) else 0
        else:
            kind = 0 if is_sub else 1  # a base major/honours beats an option/spec/minor
        credentialed = int(any(c in t for c in _CREDENTIALS))
        # Student's own program context first, then base-vs-sub intent.
        return (ctx, kind, overlap, credentialed, -len(t))

    return sorted(programs, key=score, reverse=True)


def _requirements_text(detail: dict) -> str:
    parts: list[str] = []
    for field in ("courseRequirementsNoUnits", "graduationRequirements", "additionalConstraints"):
        raw = detail.get(field)
        if isinstance(raw, str) and raw.strip():
            parts.append(_TAG_RE.sub(" ", raw))
    text = re.sub(r"\s+", " ", " ".join(parts))
    # Line-break before requirement-group markers so it reads as a checklist.
    text = re.sub(r"\s*(Complete |Choose |Required Courses|One of|One course|Two courses)", r"\n\1", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def program_url(pid: str) -> str:
    return f"{_PAGE}#/programs/{pid}"


def requirements_for(query: str, program: str | None = None) -> tuple[str, str, str] | None:
    """Return (program_title, requirement_text, catalog_url) for a program query.

    ``program`` (the student's own program) disambiguates same-titled sub-plans
    — "business specialization" resolves to the Mathematical Studies one for a
    Math Studies student, the CS one for a CS student.
    """

    cid = _catalog_id()
    for match in _ranked(query, _search_union(query), program)[:4]:
        def _producer(pid: str = match["pid"]) -> dict:
            try:
                return _get_json(f"{_HOST}/api/v1/catalog/program/{cid}/{pid}")
            except Exception:
                return {}

        try:
            detail = get_or_set(f"kuali:program:{match['pid']}", _CACHE_TTL, _producer)
        except Exception:
            detail = {}
        text = _requirements_text(detail)
        if text:
            return detail.get("title", match["title"]), text, program_url(match["pid"])
    return None
