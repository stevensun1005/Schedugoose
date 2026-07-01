"""Thin LLM client wrapper with graceful degradation + structured output.

Free-tier defaults (no credit card): Groq first, then OpenRouter. Groq does
**not** support LangChain ``json_schema`` on all models — we use JSON-in-prompt
instead, with an 8B fallback when the 70B tier is rate-limited.
"""

from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_GROQ_BASE = "https://api.groq.com/openai/v1"
_GROQ_MODEL = "llama-3.1-8b-instant"
_GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def _has_key(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def llm_available() -> bool:
    return any(_has_key(k) for k in (
        "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ))


def require_llm() -> bool:
    """Whether the running app must have an LLM (no offline rule-based mode).

    Defaults to on. The library still degrades gracefully for unit tests / the
    offline eval, but the API refuses to answer with rules-only when this is set.
    """

    return os.getenv("SCHEDUGOOSE_REQUIRE_LLM", "1").strip().lower() not in ("0", "false", "no", "off")


def llm_ready() -> bool:
    """True when the app can serve LLM-backed responses."""

    return llm_available()


def llm_provider() -> str | None:
    if _has_key("GROQ_API_KEY"):
        return "groq"
    if _has_key("OPENROUTER_API_KEY"):
        return "openrouter"
    if _has_key("OPENAI_API_KEY"):
        base = os.getenv("OPENAI_API_BASE", "")
        if "groq.com" in base:
            return "groq"
        if "openrouter.ai" in base:
            return "openrouter"
        return "openai"
    if _has_key("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def llm_model() -> str | None:
    provider = llm_provider()
    if provider == "groq":
        return os.getenv("GROQ_MODEL", _GROQ_MODEL)
    if provider == "openrouter":
        return os.getenv("OPENROUTER_MODEL", _OPENROUTER_MODEL)
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    return None


def llm_mode_label() -> str:
    provider = llm_provider()
    if not provider:
        return "rule-based (set GROQ_API_KEY for free LLM)"
    if provider in ("groq", "openrouter"):
        return f"{provider} (free tier)"
    return provider


def _resolve_openai_compat(*, use_fallback: bool = False) -> tuple[str, str, str] | None:
    if _has_key("GROQ_API_KEY"):
        model = (
            os.getenv("GROQ_FALLBACK_MODEL", _GROQ_FALLBACK_MODEL)
            if use_fallback
            else os.getenv("GROQ_MODEL", _GROQ_MODEL)
        )
        return os.environ["GROQ_API_KEY"].strip(), model, _GROQ_BASE
    if _has_key("OPENROUTER_API_KEY"):
        return (
            os.environ["OPENROUTER_API_KEY"].strip(),
            os.getenv("OPENROUTER_MODEL", _OPENROUTER_MODEL),
            _OPENROUTER_BASE,
        )
    if _has_key("OPENAI_API_KEY"):
        base = os.getenv("OPENAI_API_BASE", "").strip() or "https://api.openai.com/v1"
        model = os.getenv("OPENAI_MODEL", _GROQ_MODEL if "groq.com" in base else "gpt-4o-mini")
        return os.environ["OPENAI_API_KEY"].strip(), model, base
    return None


def _anthropic_client():
    try:
        from langchain_anthropic import ChatAnthropic  # type: ignore
    except Exception:
        return None
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    try:
        return ChatAnthropic(model=model, temperature=0)
    except Exception:
        return None


def _openai_compatible_client(api_key: str, model: str, base_url: str):
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
    except Exception:
        return None
    try:
        return ChatOpenAI(model=model, temperature=0, api_key=api_key, base_url=base_url)
    except Exception:
        return None


def _client(*, use_fallback: bool = False):
    compat = _resolve_openai_compat(use_fallback=use_fallback)
    if compat:
        return _openai_compatible_client(*compat)
    if _has_key("ANTHROPIC_API_KEY") and not use_fallback:
        return _anthropic_client()
    return None


def _is_rate_limit(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate_limit" in text or "rate limit" in text


def _invoke(client: Any, messages: list[tuple[str, str]]) -> Any:
    try:
        return client.invoke(messages)
    except Exception as exc:
        if _is_rate_limit(exc) and llm_provider() == "groq":
            fb = _client(use_fallback=True)
            if fb is not None:
                return fb.invoke(messages)
        raise


def _schema_hint(schema: type[BaseModel]) -> str:
    """Compact example — full JSON Schema makes Groq echo the schema back."""

    if schema.__name__ == "TurnUnderstanding":
        return (
            "Return ONE JSON object with your analysis (never echo a JSON Schema). "
            'intent must be one of: course_lookup, requirements_qa, plan_revision, career_advice, '
            "onboarding, general.\n"
            "Example:\n"
            '{"intent":"plan_revision","course_codes":["CS 246"],"program":null,'
            '"residency":null,"sequence":null,"start_term":null,"career_goal":null,'
            '"specializations":[],"minors":[],"suggested_electives":[],"elective_skip":false,'
            '"term_requirements":{"2A":["CS 246"]},"term_avoid":{"2A":["ENGL 119"]},'
            '"solver":{"min_easy_courses":0}}'
        )
    return (
        "Respond with a single valid JSON object only (no markdown). "
        f"Top-level keys: {', '.join(schema.model_fields.keys())}"
    )


def _is_schema_echo(raw: dict[str, Any]) -> bool:
    """Reject when the model returns JSON Schema metadata instead of values."""

    if "$defs" in raw or "properties" in raw and "title" in raw:
        return True
    if raw.get("title") in ("TurnUnderstanding", "SolverConfigOutput"):
        return True
    intent = raw.get("intent")
    if isinstance(intent, dict):
        return True
    return False


def _parse_json_content(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def complete_structured(system: str, user: str, schema: type[T]) -> T | None:
    """Pydantic-validated LLM output. Groq uses JSON-in-prompt (not json_schema)."""

    if not llm_available():
        return None

    provider = llm_provider()
    json_system = f"{system}\n\n{_schema_hint(schema)}"

    if provider in ("groq", "openrouter"):
        raw = complete_json(json_system, user)
        if raw and _is_schema_echo(raw):
            raw = None
        if raw:
            try:
                return schema.model_validate(raw)
            except Exception:
                pass
        return None

    client = _client()
    if client is None:
        raw = complete_json(json_system, user)
        if not raw:
            return None
        try:
            return schema.model_validate(raw)
        except Exception:
            return None
    try:
        structured = client.with_structured_output(schema)
        return structured.invoke([("system", system), ("human", user)])
    except Exception:
        raw = complete_json(json_system, user)
        if not raw:
            return None
        try:
            return schema.model_validate(raw)
        except Exception:
            return None


def complete_json(system: str, user: str) -> dict[str, Any] | None:
    if not llm_available():
        return None
    client = _client()
    if client is None:
        return None
    try:
        resp = _invoke(
            client,
            [
                ("system", system + "\nRespond with a single valid JSON object only."),
                ("human", user),
            ],
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return _parse_json_content(text)
    except Exception:
        return None


_GROUND_SYSTEM = """You are Schedugoose, a University of Waterloo course-planning assistant.
Rewrite the FACTS below into a natural, friendly reply to the user's message.
- Keep every fact, number, course code, and term exactly as given.
- NEVER introduce a course code (e.g. ECON 201, CS 246) or requirement that is
  not already in the FACTS. Do not guess course names or numbers.
- Keep it concise. Reply in the user's language (English or Chinese).
Return only the reply."""


def grounded_reply(user_msg: str, grounded_text: str) -> tuple[str, bool]:
    """LLM-phrase a deterministic answer, grounded in its facts. Returns (text, used_llm).

    So every turn goes through the LLM in production, while the facts stay exact.
    Falls back to the deterministic text when the LLM is unavailable (tests/eval).
    """

    if not grounded_text.strip() or not llm_available():
        return grounded_text, False
    out = complete_text(_GROUND_SYSTEM, f"User message:\n{user_msg}\n\nFACTS:\n{grounded_text}")
    return (out.strip(), True) if out and out.strip() else (grounded_text, False)


def complete_text(system: str, user: str) -> str | None:
    if not llm_available():
        return None
    # Groq: try 8B first (higher quota), then 70B on failure.
    attempts = (False, True) if llm_provider() == "groq" else (False,)
    for use_fallback in attempts:
        client = _client(use_fallback=use_fallback)
        if client is None:
            continue
        try:
            resp = _invoke(client, [("system", system), ("human", user)])
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            if text and text.strip():
                return text.strip()
        except Exception:
            continue
    return None
