"""API routes."""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.graph import plan
from agent.llm import llm_available, llm_mode_label, llm_model, llm_provider
from data.rag_store import rag_backend
from data.uw_api import data_source, uw_api_status
from data.term_codes import term_code_from_start
from agent.state import PlannerState
from app import sessions
from data.program_reqs import list_programs

router = APIRouter()
_log = logging.getLogger("schedugoose")


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
    llm_understood: bool = False
    llm_explained: bool = False
    llm_configured: bool = False
    llm_parse_failed: bool = False
    llm_offline: bool = False
    llm_mode: str = ""
    graph_trace: list[str] = Field(default_factory=list)
    rag_hits: list[dict] = Field(default_factory=list)


@router.get("/health")
def health() -> dict:
    has_key = llm_available()
    provider = llm_provider()
    return {
        "status": "ok",
        "llm": has_key,
        "llm_provider": provider,
        "llm_model": llm_model(),
        "llm_mode": llm_mode_label(),
        "llm_setup": "Set GROQ_API_KEY in .env — free at https://console.groq.com/keys",
        "rag_backend": rag_backend(),
        "uw_api": bool(os.getenv("UW_API_KEY")),
        "uw_data_source": uw_api_status(),
        "uw_term_code": term_code_from_start(None),
        "graph_nodes": [
            "understand", "gather_constraints", "clarify", "retrieve", "build_model",
            "solve", "diagnose", "plan_terms", "explain",
        ],
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

    try:
        result = plan(state)
    except Exception:
        # Never 500 the chat UI: degrade to a readable reply and log the cause.
        _log.exception("plan() failed for session %s", session_id)
        result = dict(state)
        result["explanation"] = (
            "Sorry — I hit an internal error working that out. Please try rephrasing, "
            "or send your message again."
        )
        result["needs_clarification"] = True

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
        llm_understood=bool(result.get("llm_understood")),
        llm_explained=bool(result.get("llm_explained")),
        llm_configured=bool(result.get("llm_configured", llm_available())),
        llm_parse_failed=bool(result.get("llm_parse_failed")),
        llm_offline=bool(result.get("llm_offline")),
        llm_mode=llm_mode_label(),
        graph_trace=list(result.get("graph_trace") or []),
        rag_hits=list(result.get("rag_hits") or []),
    )
