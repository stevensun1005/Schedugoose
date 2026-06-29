"""Per-turn revision notes (no stale pin lines)."""

from __future__ import annotations

from agent.revision import format_turn_revision_note, revision_delta


def test_revision_delta_only_new_avoids() -> None:
    prev = {"term_avoid": {"2A": ["CS 240"]}, "must_avoid": []}
    config = {"term_avoid": {"2A": ["CS 240", "ENGL 119"]}, "must_avoid": ["MUSIC 116"]}
    delta = revision_delta(prev, config)
    assert delta["term_avoid"] == {"2A": ["ENGL 119"]}
    assert delta["must_avoid"] == ["MUSIC 116"]


def test_format_turn_note_no_stale_on_second_turn() -> None:
    plan = {
        "terms": [
            {"label": "1A", "kind": "study", "courses": ["CS 135", "MATH 135"]},
            {"label": "2A", "kind": "study", "courses": ["CS 245"]},
        ]
    }
    delta = {"term_avoid": {}, "term_requirements": {}, "must_avoid": []}
    assert format_turn_revision_note(delta, plan) == ""


def test_format_must_avoid_without_wrong_slot() -> None:
    plan = {
        "terms": [
            {"label": "1A", "kind": "study", "courses": ["CS 135"]},
        ]
    }
    delta = {"must_avoid": ["MUSIC 116"], "term_avoid": {}, "term_requirements": {}}
    note = format_turn_revision_note(delta, plan)
    assert "MUSIC 116" in note
    assert "2A" not in note
