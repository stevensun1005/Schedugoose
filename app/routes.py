"""API routes."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.graph import plan
from agent.llm import llm_available
from agent.state import PlannerState
from app import sessions
from data.program_reqs import list_programs

router = APIRouter()


class ProfileIn(BaseModel):
    completed: list[str] = Field(default_factory=list, description="Completed course codes (transcript)")


class PlanRequest(BaseModel):
    message: str = Field(..., description="Natural-language request")
    session_id: str | None = Field(None, description="Omit to start a new session")
    profile: ProfileIn | None = None


class PlanResponse(BaseModel):
    session_id: str
    needs_clarification: bool
    clarification: str | None = None
    explanation: str
    intake: dict | None = None
    config: dict | None = None
    plan: dict | None = None
    schedule: dict | None = None
    used_llm: bool


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": llm_available(),
        "uw_api": bool(os.getenv("UW_API_KEY")),
        "programs": list_programs(),
    }


@router.post("/plan", response_model=PlanResponse)
def plan_endpoint(req: PlanRequest) -> PlanResponse:
    session_id = req.session_id or uuid.uuid4().hex
    state: PlannerState = sessions.load(session_id)
    state.setdefault("messages", [])
    state["messages"].append({"role": "user", "content": req.message})

    if req.profile is not None:
        state["profile"] = req.profile.model_dump(exclude_none=True)
    state.setdefault("profile", {"completed": []})

    result = plan(state)

    # Record assistant turn and persist.
    result.setdefault("messages", state["messages"])
    result["messages"].append(
        {"role": "assistant", "content": result.get("explanation", "")}
    )
    sessions.save(session_id, result)

    return PlanResponse(
        session_id=session_id,
        needs_clarification=bool(result.get("needs_clarification")),
        clarification=result.get("clarification") or None,
        explanation=result.get("explanation", ""),
        intake=result.get("intake"),
        config=result.get("config"),
        plan=result.get("plan"),
        schedule=result.get("schedule"),
        used_llm=bool(result.get("used_llm")),
    )
