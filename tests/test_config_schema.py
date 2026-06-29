"""Tests for structured LLM config schema (Phase 2)."""

from agent.config_schema import SolverConfigOutput


def test_solver_config_output_to_dict():
    out = SolverConfigOutput(
        target_categories=["CS-AI"],
        must_include=["cs 486"],
        weights={"career": 0.6, "easy": 0.2, "prof": 0.2, "morning": 0.5, "friday": 0.0},
    )
    d = out.to_solver_dict(program_reqs={"CS-AI": 2})
    assert d["must_include"] == ["CS 486"]
    assert d["weights"]["career"] == 0.6
    assert d["program_reqs"]["CS-AI"] == 2
