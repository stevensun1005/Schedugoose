"""Onboarding intake: collect program -> sequence -> start term -> career.

Drives the guided Q&A. Each user message updates a structured ``intake`` dict;
``next_question`` returns the next missing piece so the clarify node can ask for
exactly one thing at a time, and ``is_complete`` says when planning can start.
"""

from __future__ import annotations

from typing import Any, TypedDict

from agent.semantic import has_career_hint
from data.sequences import (
    format_term,
    identify_program,
    match_sequence,
    parse_start_term,
    sequences_for_faculty,
)


class Intake(TypedDict, total=False):
    program: str
    faculty: str
    reqs_key: str
    sequence: str          # sequence key
    start_term: dict       # {"season","year"}
    career_goal: str


def update_intake(intake: Intake, text: str) -> Intake:
    """Merge any program / sequence / start-term / career info from ``text``."""

    out: Intake = dict(intake)  # type: ignore[assignment]

    if not out.get("program"):
        prog = identify_program(text)
        if prog:
            out["program"] = prog.name
            out["faculty"] = prog.faculty
            out["reqs_key"] = prog.reqs_key

    if out.get("faculty") and not out.get("sequence"):
        key = match_sequence(text, out["faculty"])
        if key:
            out["sequence"] = key

    if not out.get("start_term"):
        term = parse_start_term(text)
        if term:
            out["start_term"] = term

    if not out.get("career_goal") and has_career_hint(text):
        out["career_goal"] = text

    return out


def is_complete(intake: Intake) -> bool:
    return all(intake.get(k) for k in ("program", "sequence", "start_term", "career_goal"))


def next_question(intake: Intake) -> str:
    """Return the next onboarding question for the first missing field."""

    if not intake.get("program"):
        return (
            "What program are you in? (e.g. Computer Science, Software Engineering, "
            "Mechatronics, Statistics, Biology) -- this tells me your faculty and sequence."
        )
    if not intake.get("sequence"):
        faculty = intake.get("faculty", "")
        opts = sequences_for_faculty(faculty)
        listed = "; ".join(f"{s.name}" for s in opts) or "regular or co-op"
        return (
            f"You're in {intake.get('program')} ({faculty}). Which sequence are you in? "
            f"Options: {listed}."
        )
    if not intake.get("start_term"):
        return (
            "Which term do you start (your 1A)? e.g. \"Fall 2026\". "
            "I'll build the plan forward from there along your sequence."
        )
    if not intake.get("career_goal"):
        return (
            "What career or field are you aiming for? (e.g. data scientist, "
            "backend engineer, security). You can also tell me preferences like "
            "\"keep it light\", \"no mornings\", or \"at least one easy course\"."
        )
    return ""


def summary(intake: Intake) -> str:
    parts = []
    if intake.get("program"):
        parts.append(intake["program"])
    if intake.get("sequence"):
        parts.append(intake["sequence"])
    if intake.get("start_term"):
        parts.append(f"starting {format_term(intake['start_term'])}")
    return ", ".join(parts)
