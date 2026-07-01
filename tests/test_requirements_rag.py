"""Scalable program-requirements retrieval — works for ANY program, not hardcoded."""

from __future__ import annotations

from agent.requirements_qa import answer_program_requirements, is_requirements_question
from data.calendar import subjects_for_program
from data.requirements_rag import retrieve_program_requirements

# Kuali is stubbed to None by the global conftest fixture; individual tests
# override data.kuali.requirements_for to simulate an authoritative hit.


def test_program_maps_to_subjects_not_hardcoded_requirements():
    assert subjects_for_program("requirements for mechatronics engineering") == ["MTE"]
    assert subjects_for_program("economics minor") == ["ECON"]
    assert subjects_for_program("what about biology") == ["BIOL"]
    # A career phrase with no program is not a subject.
    assert subjects_for_program("i want to be a backend engineer") == []


def test_non_program_text_returns_none():
    assert answer_program_requirements("hello there") is None


def test_offline_points_to_official_calendar(monkeypatch):
    # No live fetch → cite the authoritative UW page instead of guessing.
    monkeypatch.setattr("data.requirements_rag.retrieve_program_requirements", lambda q, **k: ("", []))
    ans = answer_program_requirements("what are the requirements for mechatronics engineering")
    assert ans is not None
    assert "ucalendar.uwaterloo.ca" in ans and "MTE" in ans


def test_grounded_answer_uses_retrieved_context(monkeypatch):
    # With context + an LLM, the answer is generated from UW excerpts and cited.
    ctx = "MTE 100 Mechatronics Engineering. MTE 120 Chemistry. MTE 121 Digital computation."
    url = "https://ucalendar.uwaterloo.ca/2324/COURSE/course-MTE.html"
    monkeypatch.setattr("data.requirements_rag.retrieve_program_requirements", lambda q, **k: (ctx, [url]))
    import agent.llm
    monkeypatch.setattr(agent.llm, "llm_available", lambda: True)
    monkeypatch.setattr(agent.llm, "complete_text", lambda s, u: "Mechatronics starts with MTE 100, MTE 120, MTE 121.")
    ans = answer_program_requirements("mechatronics first year courses")
    assert "MTE 100" in ans and url in ans


def test_requirements_question_detects_any_program():
    assert is_requirements_question("what are the requirements for mechatronics engineering")
    assert is_requirements_question("what do i need for an economics minor")
    assert not is_requirements_question("make 2A lighter")


def test_retrieve_returns_empty_without_subject():
    ctx, urls = retrieve_program_requirements("i like turtles")
    assert ctx == "" and urls == []


def test_kuali_authoritative_path(monkeypatch):
    # When the academic-calendar API returns real requirements, use + cite them.
    url = "https://uwaterloo.ca/academic-calendar/undergraduate-studies/catalog#/programs/abc"
    monkeypatch.setattr(
        "data.kuali.requirements_for",
        lambda q: ("Mechatronics Engineering (BASc - Honours)", "Complete all: MTE 120, MTE 140.", url),
    )
    import agent.llm
    monkeypatch.setattr(agent.llm, "llm_available", lambda: True)
    monkeypatch.setattr(agent.llm, "complete_text", lambda s, u: "You take MTE 120 and MTE 140.")
    ans = answer_program_requirements("requirements for mechatronics engineering")
    assert "MTE 120" in ans and url in ans


def test_kuali_offline_returns_raw_requirements(monkeypatch):
    url = "https://uwaterloo.ca/academic-calendar/undergraduate-studies/catalog#/programs/abc"
    monkeypatch.setattr(
        "data.kuali.requirements_for",
        lambda q: ("Economics Minor", "Complete all: ECON 101, ECON 102.", url),
    )
    # llm_available is False by default (conftest clears keys) → raw text + link.
    ans = answer_program_requirements("economics minor requirements")
    assert "ECON 101" in ans and url in ans
