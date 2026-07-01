"""Course lookup: any-subject enrichment, not-found handling, requirements routing."""

from __future__ import annotations

from agent.course_qa import answer_course_question, gather_course_facts
from agent.intent_schema import TurnUnderstanding
from agent.understand import wants_requirements_qa


def test_nonexistent_course_not_invented():
    facts = {"course_id": "CS 999", "found": False}
    text, used = answer_course_question("what is CS 999", facts)
    assert "couldn't find" in text.lower() and "CS 999" in text
    assert used is False


def test_any_subject_enriched_from_calendar(monkeypatch):
    # A course not in the bundled catalog gets its blurb from the UW calendar.
    monkeypatch.setattr(
        "data.calendar.course_blurb",
        lambda cid: ("MTE 100 Materials and Manufacturing. Intro to mechatronics.",
                     "https://ucalendar.uwaterloo.ca/2324/COURSE/course-MTE.html"),
    )
    facts = gather_course_facts("MTE 100")
    assert facts["found"] is True
    assert "mechatronics" in (facts.get("description") or "").lower()


def test_confirmed_absent_course_flagged(monkeypatch):
    # lookup that returns found=False (checked & absent) → not-found answer.
    monkeypatch.setattr("data.calendar.course_blurb", lambda cid: None)
    monkeypatch.setattr("agent.course_qa.lookup_course", lambda cid, **k: {"course_id": "ZZZ 100", "found": False})
    facts = gather_course_facts("ZZZ 100")
    assert facts.get("found") is False


def test_requirements_routing_beats_misclassified_intent():
    # Even if the LLM labels it career_advice, a specialization-requirements
    # question routes to the authoritative requirements answer.
    state = {
        "messages": [{"role": "user", "content": "what does the AI specialization require"}],
        "understanding": TurnUnderstanding(intent="career_advice").to_state_dict(),
    }
    assert wants_requirements_qa(state) is True
