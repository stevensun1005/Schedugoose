"""Pydantic schema for structured LLM output (semantic layer).

The LLM translates natural language into this typed object. The OR solver
never sees raw text — only :meth:`SolverConfigOutput.to_solver_dict`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CreditLoad(BaseModel):
    min: float = Field(2.0, ge=0.0, le=5.0)
    max: float = Field(2.5, ge=0.0, le=5.0)


class WeightsOut(BaseModel):
    career: float = Field(0.5, ge=0.0, le=1.0)
    easy: float = Field(0.3, ge=0.0, le=1.0)
    prof: float = Field(0.2, ge=0.0, le=1.0)
    morning: float = Field(0.0, ge=0.0, le=1.0)
    friday: float = Field(0.0, ge=0.0, le=1.0)


class TimePrefs(BaseModel):
    avoid_before: str | None = None
    avoid_friday: bool = False


class SolverConfigOutput(BaseModel):
    """Structured config emitted by the LLM semantic layer."""

    target_categories: list[str] = Field(default_factory=list)
    credit_load: CreditLoad = Field(default_factory=CreditLoad)
    weights: WeightsOut = Field(default_factory=WeightsOut)
    time_prefs: TimePrefs = Field(default_factory=TimePrefs)
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    min_easy_courses: int = Field(0, ge=0, le=5)

    @field_validator("must_include", "must_avoid", mode="before")
    @classmethod
    def _normalize_codes(cls, v: object) -> list[str]:
        if not v:
            return []
        return [str(c).strip().upper() for c in v]  # type: ignore[union-attr]

    def to_solver_dict(self, *, program_reqs: dict[str, int] | None = None) -> dict:
        return {
            "target_categories": list(self.target_categories),
            "credit_load": self.credit_load.model_dump(),
            "weights": self.weights.model_dump(),
            "time_prefs": self.time_prefs.model_dump(exclude_none=True),
            "must_include": list(self.must_include),
            "must_avoid": list(self.must_avoid),
            "min_easy_courses": self.min_easy_courses,
            "program_reqs": dict(program_reqs or {}),
        }
