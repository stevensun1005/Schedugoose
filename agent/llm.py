"""Thin LLM client wrapper with graceful degradation.

The LLM only **translates** (NL -> config) and **explains**. If no
``ANTHROPIC_API_KEY`` is configured or the LLM stack isn't installed, every
function returns ``None`` and callers fall back to deterministic logic, so the
whole system still runs end-to-end offline.
"""

from __future__ import annotations

import json
import os
from typing import Any


def llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _client():
    try:
        from langchain_anthropic import ChatAnthropic  # type: ignore
    except Exception:
        return None
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    try:
        return ChatAnthropic(model=model, temperature=0)
    except Exception:
        return None


def complete_json(system: str, user: str) -> dict[str, Any] | None:
    """Ask the LLM for a JSON object. Returns ``None`` if unavailable / on error."""

    if not llm_available():
        return None
    client = _client()
    if client is None:
        return None
    try:
        resp = client.invoke(
            [
                ("system", system + "\nRespond with a single valid JSON object only."),
                ("human", user),
            ]
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def complete_text(system: str, user: str) -> str | None:
    """Ask the LLM for free-form text. Returns ``None`` if unavailable / on error."""

    if not llm_available():
        return None
    client = _client()
    if client is None:
        return None
    try:
        resp = client.invoke([("system", system), ("human", user)])
        return resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception:
        return None
