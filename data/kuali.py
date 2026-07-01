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


def search_programs(query: str, limit: int = 8) -> list[dict]:
    cid = _catalog_id()
    key = f"kuali:search:{query.lower()}"

    def _producer() -> list[dict]:
        try:
            data = _get_json(f"{_HOST}/api/v1/catalog/search/{cid}?q={httpx.QueryParams({'q': query})['q']}")
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
    """Search the cleaned query and its strongest term; merge (Kuali ranks
    single strong terms better than multi-word phrases)."""

    terms = _clean_terms(query)
    queries = [" ".join(terms) if terms else query]
    if terms:
        longest = max(terms, key=len)
        if longest != queries[0]:
            queries.append(longest)
    seen: set[str] = set()
    merged: list[dict] = []
    for q in queries:
        for p in search_programs(q):
            if p["pid"] not in seen:
                seen.add(p["pid"])
                merged.append(p)
    return merged


_COURSE_CODE = re.compile(r"^[A-Z]{2,6}\s?\d{3}[A-Z]?$")
_CREDENTIALS = ("bachelor", "honours", "minor", "specialization", "option", "major", "diploma")


def _ranked(query: str, results: list[dict]) -> list[dict]:
    """Programs (not course entries) ranked by relevance to the query."""

    low = query.lower()
    want_minor = "minor" in low
    want_spec = "special" in low or "spec" in low
    terms = _clean_terms(query)
    programs = [p for p in results if not _COURSE_CODE.match(p.get("code", "").strip())]

    def score(p: dict) -> tuple:
        t = p["title"].lower()
        overlap = sum(1 for w in terms if w in t)
        credentialed = int(any(c in t for c in _CREDENTIALS))
        if want_minor:
            kind = 1 if "minor" in t else 0
        elif want_spec:
            kind = 1 if ("special" in t or "option" in t) else 0
        else:
            kind = 1 if ("minor" not in t and "special" not in t) else 0
        return (overlap, kind, credentialed, -len(t))

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


def requirements_for(query: str) -> tuple[str, str, str] | None:
    """Return (program_title, requirement_text, catalog_url) for a program query."""

    cid = _catalog_id()
    for match in _ranked(query, _search_union(query))[:4]:
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
