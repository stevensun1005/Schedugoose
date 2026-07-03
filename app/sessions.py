"""Multi-turn session memory.

Session state is persisted in Redis when ``REDIS_URL`` is set; otherwise it is
kept in-process AND mirrored to local JSON files, so a server restart doesn't
lose conversations. This is what lets "change one sentence, re-plan" remember
the prior config.
"""

from __future__ import annotations

import json
import os

from agent.state import PlannerState

_MEMORY: dict[str, str] = {}
_SESSION_TTL_S = 60 * 60 * 6  # 6 hours
_FILE_DIR = os.getenv("SESSION_DIR", os.path.join("data", "sessions"))


def _file_path(session_id: str) -> str:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:64]
    return os.path.join(_FILE_DIR, f"{safe}.json")


def _file_load(session_id: str) -> str | None:
    try:
        path = _file_path(session_id)
        if not os.path.exists(path):
            return None
        import time

        if time.time() - os.path.getmtime(path) > _SESSION_TTL_S:
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _file_save(session_id: str, raw: str) -> None:
    try:
        os.makedirs(_FILE_DIR, exist_ok=True)
        with open(_file_path(session_id), "w", encoding="utf-8") as fh:
            fh.write(raw)
    except Exception:
        pass  # best-effort — in-process memory still holds the session


def _redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _key(session_id: str) -> str:
    return f"schedugoose:session:{session_id}"


def load(session_id: str) -> PlannerState:
    client = _redis()
    if client is not None:
        try:
            raw = client.get(_key(session_id))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    raw = _MEMORY.get(session_id) or _file_load(session_id)
    return json.loads(raw) if raw else PlannerState(messages=[])


def save(session_id: str, state: PlannerState) -> None:
    # Persist only JSON-serializable fields (drop live Course objects).
    persist = {k: v for k, v in state.items() if k not in ("candidates", "catalog", "conflicts")}
    raw = json.dumps(persist, default=str)
    client = _redis()
    if client is not None:
        try:
            client.setex(_key(session_id), _SESSION_TTL_S, raw)
            return
        except Exception:
            pass
    _MEMORY[session_id] = raw
    _file_save(session_id, raw)
