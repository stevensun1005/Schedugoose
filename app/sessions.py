"""Multi-turn session memory.

Session state is persisted in Redis when ``REDIS_URL`` is set, else in-process.
This is what lets "change one sentence, re-plan" remember the prior config.
"""

from __future__ import annotations

import json
import os

from agent.state import PlannerState

_MEMORY: dict[str, str] = {}
_SESSION_TTL_S = 60 * 60 * 6  # 6 hours


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
    raw = _MEMORY.get(session_id)
    return json.loads(raw) if raw else PlannerState(messages=[])


def save(session_id: str, state: PlannerState) -> None:
    # Persist only JSON-serializable fields (drop live Course objects).
    persist = {k: v for k, v in state.items() if k != "candidates"}
    raw = json.dumps(persist, default=str)
    client = _redis()
    if client is not None:
        try:
            client.setex(_key(session_id), _SESSION_TTL_S, raw)
            return
        except Exception:
            pass
    _MEMORY[session_id] = raw
