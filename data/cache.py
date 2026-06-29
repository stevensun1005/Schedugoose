"""Tiny cache abstraction.

Uses Redis when ``REDIS_URL`` is set (UW Open Data has rate limits -- cache
retrieval results), otherwise an in-process dict. Values are JSON-serializable.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

_MEMORY: dict[str, tuple[float, str]] = {}


def _redis_client():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def get_or_set(key: str, ttl_s: int, producer: Callable[[], Any]) -> Any:
    """Return cached JSON value for ``key`` or compute, store, and return it."""

    client = _redis_client()
    if client is not None:
        try:
            cached = client.get(key)
            if cached is not None:
                return json.loads(cached)
            value = producer()
            client.setex(key, ttl_s, json.dumps(value))
            return value
        except Exception:
            pass  # fall through to memory cache on any Redis hiccup

    now = time.time()
    hit = _MEMORY.get(key)
    if hit and hit[0] > now:
        return json.loads(hit[1])
    value = producer()
    _MEMORY[key] = (now + ttl_s, json.dumps(value))
    return value
