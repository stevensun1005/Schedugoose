"""Degree audit: ✅/❌ requirement checklist against the transcript."""

from __future__ import annotations

from agent.audit import (
    audit_reply,
    component_whatif_reply,
    degree_audit_reply,
    wants_component_whatif,
    wants_degree_audit,
)

_GROUPS = [
    {"label": "One of MATH 225/MATH 235/MATH 245", "count": 1,
     "courses": ["MATH 225", "MATH 235", "MATH 245"], "subjects": [], "min_level": 0},
    {"label": "10 × 300+-level (CO/CS/MATH/STAT)", "count": 10,
     "courses": [], "subjects": ["CO", "CS", "MATH", "STAT"], "min_level": 300},
]


def _state(msg: str, completed: list[str]) -> dict:
    return {
        "intake": {"program": "Mathematical Studies", "faculty": "Math",
                   "reqs_key": "MathStudies-Major", "completed": completed,
                   "live_reqs": {"title": "Mathematical Studies", "url": "https://x", "groups": _GROUPS}},
        "profile": {"completed": completed},
        "messages": [{"role": "user", "content": msg}],
    }


def test_detects_audit_and_whatif_phrases() -> None:
    assert wants_degree_audit(_state("help me check my degree requirements", []))
    assert wants_degree_audit(_state("帮我check一下毕业条件", []))
    assert wants_component_whatif(_state("if I add a statistics minor, what else do I need?", []))
    assert not wants_degree_audit(_state("make 2A lighter", []))
    assert not wants_component_whatif(_state("what does the AI specialization require", []))


def test_checklist_marks_satisfied_and_missing() -> None:
    completed = ["MATH 135", "MATH 225", "STAT 230", "STAT 231", "STAT 341", "CS 330"]
    text = degree_audit_reply(_state("check my degree", completed))
    # Non-honours option satisfies its group and is named.
    assert "✅ One of MATH 225/MATH 235/MATH 245 — satisfied by MATH 225" in text
    # Level rule shows progress, the gap, and eligible recommendations.
    assert "❌ 10 × 300+-level" in text and "need 8 more" in text
    assert "you could take:" in text
    assert "Source: https://x" in text


def test_checklist_recommendations_are_eligible_only() -> None:
    completed = ["MATH 225", "STAT 230", "STAT 231"]
    text = degree_audit_reply(_state("check my degree", completed))
    # STAT 3xx (prereq met, open) recommended; CS-major-only 3xx/4xx are not.
    assert "STAT 330" in text
    for cs_only in ("CS 341", "CS 348", "CS 480", "CS 486", "CS 492"):
        assert cs_only not in text, cs_only


def test_audit_without_transcript_asks_for_it() -> None:
    text = degree_audit_reply(_state("check my degree", []))
    assert "transcript" in text.lower()


def test_whatif_uses_curated_fallback_offline() -> None:
    # kuali is mocked to None in conftest -> curated Stats-Minor categories.
    completed = ["STAT 230", "STAT 231", "STAT 341", "MATH 235"]
    text = component_whatif_reply(_state("if I add a stats minor what else do I need", completed))
    assert text is not None
    assert "✅" in text or "❌" in text


def test_audit_reply_routes_and_declines_other_turns() -> None:
    assert audit_reply(_state("check my degree", ["MATH 225"])) is not None
    assert audit_reply(_state("what is CS 246", ["MATH 225"])) is None
