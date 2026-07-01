"""GenAI + MLOps infrastructure: chunking, embeddings, hybrid RAG, ETL, metrics."""

from __future__ import annotations

import warnings

from data.chunking import chunk_documents, chunk_text
from data.embeddings import BM25, cosine, embed, embed_batch, tokenize
from data.etl import run_pipeline, transform
from data.feedback import export_sft, log_interaction, to_sft_record
from data.rag_store import hybrid_retrieve, retrieve_career_context


# --- chunking ---------------------------------------------------------------
def test_chunking_respects_size_and_overlap():
    text = ". ".join(f"sentence number {i} here" for i in range(60))
    chunks = chunk_text(text, source="doc", max_chars=120, overlap_chars=30)
    assert len(chunks) > 1
    assert all(len(c.text) <= 120 for c in chunks)
    assert all(c.source == "doc" for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunking_hard_splits_oversized_sentence():
    chunks = chunk_text("x" * 1000, max_chars=100)
    assert chunks and all(len(c.text) <= 100 for c in chunks)


def test_chunk_documents_flattens():
    out = chunk_documents({"a": "one. two. three.", "b": "four. five."}, max_chars=20)
    assert {c.source for c in out} == {"a", "b"}


# --- embeddings -------------------------------------------------------------
def test_embed_is_deterministic_and_normalized():
    v1, v2 = embed("machine learning"), embed("machine learning")
    assert v1 == v2
    assert abs(cosine(v1, v1) - 1.0) < 1e-6


def test_related_text_more_similar_than_unrelated():
    a = embed("statistics and probability")
    close = embed("probability and statistics course")
    far = embed("distributed operating systems kernels")
    assert cosine(a, close) > cosine(a, far)


def test_bm25_ranks_matching_doc_first():
    corpus = [tokenize(t) for t in ["machine learning and ai", "operating systems", "databases sql"]]
    bm = BM25(corpus)
    scores = bm.scores(tokenize("machine learning"))
    assert scores[0] == max(scores)


# --- hybrid RAG -------------------------------------------------------------
def test_hybrid_retrieval_keyword_match():
    hits = hybrid_retrieve("backend distributed systems", top_k=1)
    assert hits and hits[0][0].career == "backend engineer"


def test_hybrid_retrieval_semantic_paraphrase():
    # No lexical overlap with "data scientist" — dense signal must carry it.
    hits = hybrid_retrieve("i want to teach computers to learn from data", top_k=2)
    assert "data scientist" in {h.career for h, _ in hits}


def test_retrieve_career_context_uses_hybrid_offline():
    hits, cats, codes = retrieve_career_context("data science")
    assert hits[0].source == "hybrid"
    assert codes and cats


# --- ETL --------------------------------------------------------------------
def test_etl_pipeline_produces_embedded_chunks(tmp_path):
    out = tmp_path / "vs.json"
    stats = run_pipeline(out_path=str(out))
    assert stats.documents > 0
    assert stats.chunks == stats.embedded > 0
    assert out.exists()


def test_transform_embeds_each_chunk():
    recs = transform({"CS 246": "Object oriented software. Design patterns and testing."}, max_chars=40)
    assert recs and all(r.embedding and r.id.startswith("CS 246#") for r in recs)


# --- finetuning data prep ---------------------------------------------------
def test_feedback_logging_and_sft_export(tmp_path):
    log = tmp_path / "interactions.jsonl"
    log_interaction(system="s", user="make 2A lighter", assistant="done", reward=1, path=str(log))
    log_interaction(system="s", user="hi", assistant="hey", reward=-1, path=str(log))
    out = tmp_path / "sft.jsonl"
    kept = export_sft(str(out), src=str(log), min_reward=1)
    assert kept == 1  # only the positively-rewarded turn
    rec = to_sft_record({"system": "s", "user": "u", "assistant": "a"})
    assert [m["role"] for m in rec["messages"]] == ["system", "user", "assistant"]


# --- metrics + endpoint -----------------------------------------------------
def test_metrics_endpoint_and_recording(monkeypatch):
    warnings.filterwarnings("ignore")
    # Run offline so the request is fast and deterministic (no live LLM call);
    # allow the rules path for this metrics check.
    for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "UW_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SCHEDUGOOSE_REQUIRE_LLM", "0")
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    c.post("/plan", json={"message": "hi", "profile": {"completed": []}})
    snap = c.get("/metrics").json()
    assert snap["counters"]["plan_requests_total"] >= 1
    assert "latency_ms" in snap
    prom = c.get("/metrics", params={"format": "prometheus"}).text
    assert "schedugoose_up 1" in prom
