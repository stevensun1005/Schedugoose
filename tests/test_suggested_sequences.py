"""Official SCS suggested-sequence charts (transcribed from the 2022-23 PDFs)."""

from __future__ import annotations

from data.suggested_sequences import CHARTS, chart_key_for, format_chart


def test_all_five_charts_present_with_both_streams() -> None:
    assert set(CHARTS) == {"BCS", "BMath (CS)", "BCS/SE", "BCS/DH", "BMath (CS/DH)"}
    for chart in CHARTS.values():
        for stream in ("cs115", "cs135"):
            seq = chart[stream]
            assert set(seq) == {"1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"}


def test_chart_selection_by_program_and_option() -> None:
    assert chart_key_for("suggested sequence", "Computer Science") == "BCS"
    assert chart_key_for("bmath cs suggested sequence") == "BMath (CS)"
    assert chart_key_for("digital hardware sequence for bmath") == "BMath (CS/DH)"
    assert chart_key_for("bcs software engineering option sequence") == "BCS/SE"
    assert chart_key_for("sequence for biology") is None


def test_format_matches_official_chart_content() -> None:
    text = format_chart("BMath (CS)", "cs135")
    # Straight from the chart: MATH 235/237 land in 2A, CS 341 in 3B.
    assert "2A: CS 246, CS 245, MATH 235, MATH 237, STAT 230" in text
    assert "3B: CS 341" in text
    assert "cs.uwaterloo.ca/suggested-sequences" in text


def test_timeline_matches_official_chart() -> None:
    from data.program_templates import recommended_term

    assert recommended_term("CS 246") == "2A"
    assert recommended_term("MATH 239") == "2B"   # chart: 2B, not 2A
    assert recommended_term("STAT 231") == "3A"   # chart: 3A, not 2B
    assert recommended_term("CS 341") == "3B"     # chart: 3B, not 3A


def test_explain_routes_sequence_question() -> None:
    from agent.nodes.explain import explain

    state = {
        "intake": {"program": "Computer Science"}, "config": {}, "plan": None,
        "messages": [{"role": "user", "content": "what is the suggested course sequence?"}],
    }
    out = explain(state)["explanation"]
    assert "official suggested sequence" in out
    assert "1A:" in out and "Source:" in out
