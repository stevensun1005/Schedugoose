"""Tests for natural chat during onboarding."""

from __future__ import annotations

from agent.converse import conversational_reply, _fallback_reply
from agent.graph import run_turn
from agent.intent_schema import TurnUnderstanding


def test_fallback_hi(monkeypatch) -> None:
    monkeypatch.setattr("agent.converse.llm_available", lambda: False)
    state = {
        "messages": [{"role": "user", "content": "hi"}],
        "intake": {},
        "needs_clarification": True,
    }
    text, used = conversational_reply(state)
    assert not used
    assert "Schedugoose" in text or "program" in text.lower()
    assert "What program are you in?" not in text or text.count("?") >= 1


def test_fallback_why_not_talking(monkeypatch) -> None:
    monkeypatch.setattr("agent.converse.llm_available", lambda: False)
    state = {
        "messages": [{"role": "user", "content": "why you are not talking with me"}],
        "intake": {},
        "needs_clarification": True,
    }
    text = _fallback_reply(state)
    assert "sorry" in text.lower() or "Sorry" in text
    assert "program" in text.lower() or "studying" in text.lower()


def test_run_turn_hi_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr("agent.converse.llm_available", lambda: True)
    monkeypatch.setattr(
        "agent.nodes.gather.understand_turn",
        lambda text, state: (TurnUnderstanding(intent="general"), True),
    )
    monkeypatch.setattr(
        "agent.converse.complete_text",
        lambda system, user: "Hey! Great to meet you — what program are you at UW?",
    )
    out = run_turn({"messages": [{"role": "user", "content": "hi"}], "intake": {}})
    assert out.get("used_llm")
    assert "Hey" in out.get("explanation", "")
    assert out["explanation"] != (
        "What program are you in? (e.g. Computer Science, Software Engineering, "
        "Mechatronics, Statistics) -- this sets your faculty and graduation rules."
    )
