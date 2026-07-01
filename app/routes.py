"""API routes."""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from agent.graph import plan
from agent.llm import llm_available, llm_mode_label, llm_model, llm_provider, llm_ready, require_llm
from data.rag_store import rag_backend
from data.uw_api import data_source, uw_api_status
from data.term_codes import term_code_from_start
from agent.state import PlannerState, last_user_message
from app import sessions
from app.metrics import METRICS
from data import feedback
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
        "llm_required": require_llm(),
        "llm_ready": llm_ready(),
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


class FeedbackRequest(BaseModel):
    session_id: str
    reward: int = Field(..., description="+1 (👍) or -1 (👎)")


@router.post("/feedback")
def feedback_endpoint(req: FeedbackRequest) -> dict:
    """Record a thumbs rating on the last turn → labelled finetuning data."""

    state = sessions.load(req.session_id)
    messages = state.get("messages") or []
    user = last_user_message(state)
    assistant = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "assistant"), "")
    if user and assistant:
        feedback.log_interaction(
            system="schedugoose-turn", user=user, assistant=assistant,
            reward=1 if req.reward >= 0 else -1, tags=["rated"],
        )
        METRICS.incr("feedback_positive_total" if req.reward >= 0 else "feedback_negative_total")
    return {"ok": True}


@router.post("/transcript")
async def transcript_endpoint(file: UploadFile) -> dict:
    """UWFlow-style transcript upload: PDF or text file -> completed course codes.

    Extraction only — the frontend feeds the codes back through the normal chat
    flow so the LLM pipeline (standing, plan skip) handles them like a paste.
    """

    from agent.semantic import extract_course_codes

    raw = await file.read()
    name = (file.filename or "").lower()
    text = ""
    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                # Quest transcripts are AES-encrypted with an empty user
                # password (owner-locked for printing, readable by anyone).
                reader.decrypt("")
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # password-protected / scanned-image PDF etc.
            _log.warning("transcript pdf extract failed: %s", exc)
            return {"ok": False, "courses": [],
                    "error": "Couldn't read that PDF — try copy-pasting the text instead."}
    else:
        text = raw.decode("utf-8", errors="ignore")

    codes = extract_course_codes(text)
    METRICS.incr("transcript_uploads_total")
    if not codes:
        return {"ok": False, "courses": [],
                "error": "No course codes found in that file — try pasting the text into the chat."}
    return {"ok": True, "courses": codes}


@router.get("/metrics")
def metrics(format: str = "json"):
    """Observability endpoint: request/latency/LLM-usage/RAG metrics."""

    if format == "prometheus":
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(METRICS.prometheus())
    return METRICS.snapshot()


@router.post("/plan", response_model=PlanResponse)
def plan_endpoint(req: PlanRequest) -> PlanResponse:
    session_id = req.session_id or uuid.uuid4().hex

    # LLM-required mode: never answer with rules-only. Fail clearly instead.
    if require_llm() and not llm_ready():
        return PlanResponse(
            session_id=session_id,
            needs_clarification=True,
            explanation=(
                "The assistant needs an LLM API key to run. Set GROQ_API_KEY (free at "
                "console.groq.com/keys) in .env and restart the server."
            ),
            used_llm=False,
            llm_configured=False,
            llm_mode=llm_mode_label(),
        )

    state: PlannerState = sessions.load(session_id)
    state.setdefault("messages", [])
    state["messages"].append({"role": "user", "content": req.message})

    if req.profile is not None:
        state["profile"] = req.profile.model_dump(exclude_none=True)
    state.setdefault("profile", {"completed": []})

    try:
        with METRICS.timer():
            result = plan(state)
    except Exception:
        # Never 500 the chat UI: degrade to a readable reply and log the cause.
        _log.exception("plan() failed for session %s", session_id)
        METRICS.incr("errors_total")
        result = dict(state)
        result["explanation"] = (
            "Sorry — I hit an internal error working that out. Please try rephrasing, "
            "or send your message again."
        )
        result["needs_clarification"] = True

    rag_hits = result.get("rag_hits") or []
    METRICS.record_turn(
        used_llm=bool(result.get("used_llm")),
        llm_parse_failed=bool(result.get("llm_parse_failed")),
        rag_source=(rag_hits[0].get("source") if rag_hits else None),
    )

    # Collect LLM turns as future supervised-finetuning data (best-effort).
    if result.get("used_llm") and result.get("explanation"):
        u = (result.get("understanding") or {})
        feedback.log_interaction(
            system="schedugoose-turn",
            user=req.message,
            assistant=result.get("explanation", ""),
            tags=[str(u.get("intent") or "")],
        )
    _log.info(
        "plan session=%s intent_llm=%s replanned=%s has_plan=%s",
        session_id, result.get("llm_understood"), result.get("replanned"), bool(result.get("plan")),
    )

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
