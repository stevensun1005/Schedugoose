"""Quest transcript parsing: grades decide completed vs failed vs in-progress."""

from __future__ import annotations

from data.transcript import looks_like_transcript, parse_transcript

# Synthesized Quest-format text (structure mirrors a real export; no real data).
_QUEST = """
University of Waterloo
Undergraduate Unofficial Transcript
Beginning of Undergraduate Record

Fall 2023
Program: (Double Degree) Business Administration (WLU) and Computer Science (UW), Honours
   Level:           1A               Form Of Study: Enrolment
Course Description Attempted Earned Grade
BUS  111W Introduction to Business Organization (WLU) 0.50 0.50 C
CS  135 Designing Functional Programs 0.50 0.50 70
CS  136 Elementary Algorithm Design 0.50 0.00 58
MATH  135 Algebra for Honours Mathematics 0.50 0.50 77
MTHEL   99 First-Year Mathematics Readiness 0.00 0.00 CR
Term GPA 69.20 Term Totals 2.50 2.50
Credit for CS 136 suppressed because the same course passed in Spring 2024.

Spring 2024
Program: Computer Science, Honours
   Level:           1B               Form Of Study: Enrolment
Course Description Attempted Earned Grade
CS  136 Elementary Algorithm Design 0.50 0.50 66
CS  245 Logic and Computation 0.50 0.00 45
COMMST  225 Interviewing 0.50 0.50 80
ACTSC  221 Introductory Financial Mathematics (Non-Specialist
Level)
0.50 0.50 51
Term GPA 60.40 Term Totals 2.50 2.00

Spring 2026
Program: Mathematical Studies, Honours
   Level:           4B               Form Of Study: Enrolment
Course Description Attempted Earned Grade
CLAS  202 Love, Life, and Death in Rome
STAT  337 Introduction to Biostatistics
Milestones
End of Undergraduate Unofficial Transcript
"""


def test_detects_quest_format() -> None:
    assert looks_like_transcript(_QUEST)
    assert not looks_like_transcript("CS 135, MATH 135, done")


def test_failed_then_retaken_is_completed() -> None:
    info = parse_transcript(_QUEST)
    assert "CS 136" in info["completed"]      # failed 58, retaken 66
    assert "CS 136" not in info["failed"]


def test_failed_never_passed_is_excluded() -> None:
    info = parse_transcript(_QUEST)
    assert "CS 245" in info["failed"]
    assert "CS 245" not in info["completed"]


def test_in_progress_final_term() -> None:
    info = parse_transcript(_QUEST)
    assert info["in_progress"] == ["CLAS 202", "STAT 337"]


def test_long_subjects_wlu_and_wrapped_lines() -> None:
    info = parse_transcript(_QUEST)
    assert "COMMST 225" in info["completed"]  # 6-letter subject
    assert "BUS 111W" in info["completed"]    # WLU W-suffix
    assert "ACTSC 221" in info["completed"]   # pair wrapped to next line
    assert "MTHEL 99" in info["completed"]    # 0.00 earned but CR (milestone)


def test_program_and_level_are_latest() -> None:
    info = parse_transcript(_QUEST)
    assert info["program"] == "Mathematical Studies, Honours"
    assert info["level"] == "4B"


def test_prose_mention_does_not_override_grade() -> None:
    # "Credit for CS 136 suppressed..." appears between graded rows; it must
    # not flip CS 136's state to in_progress.
    info = parse_transcript(_QUEST)
    assert "CS 136" not in info["in_progress"]


def test_double_spaced_codes_extract_in_chat_path() -> None:
    from agent.semantic import extract_course_codes

    codes = extract_course_codes("CS  135 and COMMST  225 and HEALTH 105")
    assert codes == ["CS 135", "COMMST 225", "HEALTH 105"]
