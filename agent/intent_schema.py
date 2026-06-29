"""Structured output for LLM turn understanding (Groq → tools → answer)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agent.config_schema import SolverConfigOutput

TurnIntent = Literal[
    "course_lookup",
    "requirements_qa",
    "plan_revision",
    "career_advice",
    "onboarding",
    "general",
]

VALID_SPECIALIZATIONS = (
    "CS-Business-Specialization",
    "CS-AI-Specialization",
    "CS-Computational-Math-Specialization",
    "CS-HCI-Specialization",
)

VALID_MINORS = (
    "Stats-Minor",
    "Math-Minor",
    "Economics-Minor",
    "Psych-Minor",
)


class StartTermOut(BaseModel):
    season: str = Field(..., description="Fall, Winter, or Spring")
    year: int = Field(..., ge=2020, le=2040)


class TurnUnderstanding(BaseModel):
    """One Groq call: what the user means + planner preferences."""

    intent: TurnIntent = Field(
        default="general",
        description=(
            "course_lookup = asking about a specific course; "
            "requirements_qa = specialization/degree requirements; "
            "plan_revision = change schedule/load/times; "
            "career_advice = course recommendations or explain plan for a career goal; "
            "onboarding = profile info (program, sequence, career); "
            "general = other"
        ),
    )
    course_codes: list[str] = Field(
        default_factory=list,
        description="Course codes mentioned or implied for lookup (e.g. SOC 101). Never invent.",
    )
    program: str | None = Field(None, description="e.g. Computer Science, Software Engineering")
    residency: Literal["international", "domestic"] | None = None
    sequence: str | None = Field(None, description="co-op or regular")
    start_term: StartTermOut | None = None
    career_goal: str | None = Field(
        None,
        description=(
            "Career or field the student is aiming for, in plain language. "
            "Infer from ANY wording when intake is missing career_goal — expand "
            "abbreviations (ds, PM, quant) using context; never leave null if "
            "the user is clearly answering the career question."
        ),
    )
    specializations: list[str] = Field(
        default_factory=list,
        description=f"UW CS specialization keys, one of: {', '.join(VALID_SPECIALIZATIONS)}",
    )
    minors: list[str] = Field(
        default_factory=list,
        description=f"Minor keys: {', '.join(VALID_MINORS)}",
    )
    suggested_electives: list[str] = Field(
        default_factory=list,
        description=(
            "Elective course codes that fit the student's stated goals "
            "(e.g. business spec → ECON 101). Only real UW-style codes."
        ),
    )
    elective_skip: bool = Field(False, description="True if user wants planner to choose electives")
    term_requirements: dict[str, list[str]] = Field(
        default_factory=dict,
        description='Courses pinned to a term slot, e.g. {"2A": ["CS 245", "CS 246"]}',
    )
    term_avoid: dict[str, list[str]] = Field(
        default_factory=dict,
        description='Courses to exclude from a term, e.g. {"2A": ["CS 240"]}',
    )
    solver: SolverConfigOutput = Field(default_factory=SolverConfigOutput)

    @field_validator("career_goal", mode="before")
    @classmethod
    def _norm_career(cls, v: object) -> str | None:
        if not v:
            return None
        text = str(v).strip()
        if re.search(r"(Fall|Winter|Spring)\s*\d{4}", text, re.I):
            return None
        return text

    @field_validator("residency", mode="before")
    @classmethod
    def _norm_residency(cls, v: object) -> str | None:
        if not v:
            return None
        low = str(v).lower()
        if "international" in low or "intl" in low:
            return "international"
        if "domestic" in low:
            return "domestic"
        return None

    @field_validator("start_term", mode="before")
    @classmethod
    def _norm_start_term(cls, v: object) -> dict[str, object] | None:
        if not v:
            return None
        if isinstance(v, dict):
            return v
        text = str(v)
        m = re.search(r"(Fall|Winter|Spring)\s*(\d{4})", text, re.I)
        if m:
            return {"season": m.group(1).capitalize(), "year": int(m.group(2))}
        return None

    @field_validator("term_requirements", "term_avoid", mode="before")
    @classmethod
    def _norm_term_reqs(cls, v: object) -> dict[str, list[str]]:
        if not v:
            return {}
        out: dict[str, list[str]] = {}
        for slot, codes in dict(v).items():  # type: ignore[arg-type]
            key = str(slot).strip().upper()
            out[key] = [str(c).strip().upper() for c in (codes or [])]
        return out

    @field_validator("term_avoid", mode="after")
    @classmethod
    def _expand_subject_avoid(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        from data.course_codes import course_ids_for_subject, normalize_subject

        out: dict[str, list[str]] = {}
        for slot, codes in v.items():
            expanded: list[str] = []
            for code in codes:
                if " " in code:
                    expanded.append(code)
                    continue
                for cid in course_ids_for_subject(normalize_subject(code)):
                    if cid not in expanded:
                        expanded.append(cid)
            if expanded:
                out[slot] = expanded
        return out

    @field_validator("course_codes", "suggested_electives", mode="before")
    @classmethod
    def _norm_codes(cls, v: object) -> list[str]:
        if not v:
            return []
        return [str(c).strip().upper() for c in v]  # type: ignore[union-attr]

    @field_validator("specializations", mode="before")
    @classmethod
    def _norm_specs(cls, v: object) -> list[str]:
        if not v:
            return []
        out: list[str] = []
        for item in v:  # type: ignore[union-attr]
            key = str(item).strip()
            low = key.lower()
            if "business" in low:
                key = "CS-Business-Specialization"
            elif "ai" in low or "artificial" in low:
                key = "CS-AI-Specialization"
            elif "computational" in low and "math" in low:
                key = "CS-Computational-Math-Specialization"
            elif "hci" in low or "human-computer" in low:
                key = "CS-HCI-Specialization"
            if key in VALID_SPECIALIZATIONS and key not in out:
                out.append(key)
        return out

    def to_state_dict(self) -> dict:
        return self.model_dump()
