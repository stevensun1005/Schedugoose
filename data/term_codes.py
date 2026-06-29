"""Map calendar (season, year) to UW OpenAPI term codes."""

from __future__ import annotations

import os
from functools import lru_cache

import httpx

API_BASE = "https://openapi.data.uwaterloo.ca/v3"


@lru_cache(maxsize=1)
def _terms_index() -> dict[tuple[str, int], str]:
    """``(season, year)`` -> ``termCode`` from the live Terms endpoint."""

    key = os.getenv("UW_API_KEY")
    if not key:
        return {}
    try:
        resp = httpx.get(
            f"{API_BASE}/Terms",
            headers={"x-api-key": key, "accept": "application/json"},
            timeout=30.0,
        )
        resp.raise_for_status()
    except Exception:
        return {}

    index: dict[tuple[str, int], str] = {}
    for t in resp.json():
        name = t.get("name", "")
        code = t.get("termCode", "")
        year = None
        for y in range(2015, 2035):
            if str(y) in name:
                year = y
                break
        if year is None:
            continue
        if "Fall" in name:
            index[("Fall", year)] = code
        elif "Winter" in name:
            index[("Winter", year)] = code
        elif "Spring" in name:
            index[("Spring", year)] = code
    return index


def resolve_uw_term_code(season: str, year: int) -> str | None:
    return _terms_index().get((season, year))


def term_code_from_start(start: dict | None) -> str:
    """Best-effort UW term code for a student's 1A start term."""

    if start:
        code = resolve_uw_term_code(start.get("season", "Fall"), int(start["year"]))
        if code:
            return code
    return os.getenv("DEFAULT_TERM", "1269")
