"""Finish-up: antirequisites, semantic course search, feedback/SFT endpoint."""

from __future__ import annotations

import copy
import warnings

from agent.graph import run_turn
from data.prefilter import prefilter_candidates
from data.prereqs import antireqs_from_requirements
from data.uw_api import fetch_courses
from eval.checker import verify_plan
from scheduler.solve import solve
from scheduler.types import SolverConfig


# --- antirequisites ---------------------------------------------------------
def test_parse_antireqs():
    assert antireqs_from_requirements("Prereq: MATH 138; Antireq: STAT 220, 230, 240") == [
        "STAT 220", "STAT 230", "STAT 240"
    ]
    assert antireqs_from_requirements("Prereq: CS 136") == []


def test_stat206_antireqs_in_catalog():
    by_id = {c.course_id: c for c in fetch_courses()}
    assert set(by_id["STAT 206"].antireqs) >= {"STAT 230", "STAT 240"}


def test_prefilter_drops_antireq_of_completed():
    out = prefilter_candidates(
        fetch_courses(), completed={"STAT 230", "MATH 135"}, slot_label="2B",
        program="Software Engineering", faculty="Engineering",
    )
    assert "STAT 206" not in {c.course_id for c in out}


def test_solver_excludes_antireq_pair():
    cands = [c for c in fetch_courses() if c.course_id in ("STAT 206", "STAT 230")]
    cfg = SolverConfig(min_units=0.0, max_units=2.5, must_include=["STAT 206", "STAT 230"])
    assert solve(cands, None, cfg).feasible is False


def test_verify_plan_flags_antireq():
    plan = {"terms": [{"label": "2B", "kind": "study", "courses": ["STAT 206", "STAT 230"], "sections": []}]}
    assert verify_plan(plan)["antireq_ok"] is False


# --- semantic course search (consumes the ETL vector store) -----------------
def test_course_search_ranks_topic_course_first():
    from data.vector_store import reset, search

    reset()
    assert search("databases and sql", 1)[0][0] == "CS 348"
    assert search("machine learning", 1)[0][0] == "CS 480"
    assert search("operating systems", 1)[0][0] == "CS 350"


def _plan_state():
    s = {"messages": [], "profile": {"completed": []}}
    for m in ["first year cs", "domestic", "math co-op", "Fall 2026", "exploring"]:
        s["messages"].append({"role": "user", "content": m})
        s = run_turn(s)
        s["messages"].append({"role": "assistant", "content": s.get("explanation", "")})
    return s


def test_course_search_in_conversation():
    s = copy.deepcopy(_plan_state())
    s["messages"].append({"role": "user", "content": "which courses cover databases?"})
    s = run_turn(s)
    assert "CS 348" in s["explanation"]


# --- feedback / SFT endpoint ------------------------------------------------
def test_feedback_endpoint_records(monkeypatch, tmp_path):
    warnings.filterwarnings("ignore")
    monkeypatch.setenv("SCHEDUGOOSE_REQUIRE_LLM", "0")
    log = tmp_path / "interactions.jsonl"
    monkeypatch.setenv("FEEDBACK_LOG", str(log))
    import importlib

    import data.feedback as fb
    importlib.reload(fb)  # pick up FEEDBACK_LOG
    from fastapi.testclient import TestClient

    import app.routes as routes
    monkeypatch.setattr(routes, "feedback", fb)
    from app.main import app

    c = TestClient(app)
    r = c.post("/plan", json={"message": "hi", "profile": {"completed": []}})
    sid = r.json()["session_id"]
    assert c.post("/feedback", json={"session_id": sid, "reward": 1}).json()["ok"]
    rows = fb.load_interactions(str(log))
    assert rows and rows[-1]["reward"] == 1


def test_sessions_survive_process_restart(tmp_path, monkeypatch) -> None:
    # Without Redis, sessions are mirrored to JSON files and reload on miss.

    from app import sessions as sess

    monkeypatch.setattr(sess, "_FILE_DIR", str(tmp_path))
    sess.save("abc123", {"messages": [{"role": "user", "content": "hi"}]})
    sess._MEMORY.clear()  # simulate a restart
    state = sess.load("abc123")
    assert state["messages"][0]["content"] == "hi"
