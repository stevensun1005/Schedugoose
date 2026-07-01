"""Shared test fixtures.

The unit/integration suite is the deterministic, offline layer (the running app
is LLM-required; see ``agent.llm.require_llm``). Importing ``app.main`` loads
``.env`` into ``os.environ`` for the whole process, which would otherwise make
the LLM-grounded reply paths call a live model mid-test. This fixture clears the
provider keys before every test so behaviour is deterministic regardless of a
local ``.env``.
"""

from __future__ import annotations

import pytest

_LLM_KEYS = (
    "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "UW_API_KEY",
)


@pytest.fixture(autouse=True)
def _offline_by_default(monkeypatch):
    for key in _LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    # No live UW academic-calendar (Kuali / course-page) calls in the suite by
    # default — tests that exercise them override these. Keeps it deterministic.
    monkeypatch.setattr("data.kuali.requirements_for", lambda q: None, raising=False)
    monkeypatch.setattr("data.calendar.course_blurb", lambda cid: None, raising=False)
