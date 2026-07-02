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


def test_revision_verbs_not_treated_as_lookup():
    from agent.course_qa import is_course_info_question

    assert is_course_info_question("what is CS 246")
    assert is_course_info_question("prereqs for CS 341")
    # "add/swap/remove/put/move X …" is a plan change, not a course lookup.
    for msg in ("add PHIL 145 to 2A", "swap CS 486 for CS 480", "remove MUSIC 116",
                "put STAT 341 in 3B", "move CS 246 to 2A"):
        assert not is_course_info_question(msg), msg


def test_course_comparison_covers_both():
    from agent.course_qa import compare_courses, is_comparison

    assert is_comparison("CS 486 vs CS 480")
    text = compare_courses(["CS 486", "CS 480"])
    assert "CS 486" in text and "CS 480" in text
    assert "prereq" in text.lower()  # each course lists its prerequisites


def test_requirements_routing_beats_misclassified_intent():
    # Even if the LLM labels it career_advice, a specialization-requirements
    # question routes to the authoritative requirements answer.
    state = {
        "messages": [{"role": "user", "content": "what does the AI specialization require"}],
        "understanding": TurnUnderstanding(intent="career_advice").to_state_dict(),
    }
    assert wants_requirements_qa(state) is True


def test_subject_aliases_cover_spoken_names():
    from data.course_codes import is_known_subject, normalize_subject

    cases = {"psychology": "PSYCH", "english": "ENGL", "stats": "STAT",
             "biology": "BIOL", "french": "FR", "pure math": "PMATH",
             "combinatorics": "CO", "accounting": "AFM", "japanese": "JAPAN",
             "sociology": "SOC", "philosophy": "PHIL", "kinesiology": "KIN"}
    for spoken, code in cases.items():
        assert normalize_subject(spoken) == code, spoken
        assert is_known_subject(spoken), spoken
    # Real codes normalize to themselves; junk is not "known".
    assert normalize_subject("SYDE") == "SYDE" and is_known_subject("SYDE")
    assert not is_known_subject("XYZQ")


def test_spoken_subject_resolves_catalog_courses():
    from data.course_codes import course_ids_for_subject

    assert "FR 101" in course_ids_for_subject("french")
    assert "PSYCH 101" in course_ids_for_subject("psychology")
