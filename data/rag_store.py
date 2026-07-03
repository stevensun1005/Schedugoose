"""RAG retrieval: MongoDB Atlas Vector Search with offline fallback.

Career→course grounding must never invent codes. This module is the single
retrieval seam: vector DB when configured, else token-cosine over the curated KB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from data.embeddings import BM25, cosine, embed, embed_batch, tokenize
from data.knowledge_base import KBEntry, KNOWLEDGE_BASE


@dataclass(frozen=True)
class RAGHit:
    career: str
    score: float
    courses: tuple[str, ...]
    target_categories: tuple[str, ...]
    skills: tuple[str, ...]
    source: str  # "mongodb" | "hybrid" | "cosine"


# Precompute the sparse + dense index over the curated KB once.
_KB_DOCS = [tokenize(e.text) for e in KNOWLEDGE_BASE]
_BM25 = BM25(_KB_DOCS)
_KB_EMBED: list[list[float]] | None = None


def _kb_embeddings() -> list[list[float]]:
    global _KB_EMBED
    if _KB_EMBED is None:
        _KB_EMBED = embed_batch([e.text for e in KNOWLEDGE_BASE])
    return _KB_EMBED


def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion — combine several ranked lists into one score."""

    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return fused


def hybrid_retrieve(career_goal: str, top_k: int = 2) -> list[tuple[KBEntry, float]]:
    """Fuse BM25 (lexical) and embedding (semantic) rankings over the KB.

    Hybrid retrieval catches both exact-term matches ("machine learning") and
    semantic paraphrases ("teach computers to learn") that either signal alone
    would miss.
    """

    if not KNOWLEDGE_BASE:
        return []
    query = career_goal or ""
    sparse = _BM25.scores(tokenize(query))
    qvec = embed(query)
    dense = [cosine(qvec, ev) for ev in _kb_embeddings()]

    order = list(range(len(KNOWLEDGE_BASE)))
    sparse_rank = sorted(order, key=lambda i: sparse[i], reverse=True)
    dense_rank = sorted(order, key=lambda i: dense[i], reverse=True)
    fused = _rrf([sparse_rank, dense_rank])

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [(KNOWLEDGE_BASE[i], round(score, 4)) for i, score in ranked[:top_k]]


def _hits_from_kb(scored: list[tuple[KBEntry, float]], source: str = "cosine") -> list[RAGHit]:
    return [
        RAGHit(
            career=e.career,
            score=round(s, 4),
            courses=tuple(e.courses),
            target_categories=tuple(e.target_categories),
            skills=tuple(e.skills),
            source=source,
        )
        for e, s in scored
    ]


def _mongo_retrieve(career_goal: str, top_k: int) -> list[RAGHit] | None:
    """Best-effort MongoDB Atlas Vector Search; returns None if unavailable."""

    uri = os.getenv("MONGODB_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError:
        return None

    db_name = os.getenv("MONGODB_DB", "schedugoose")
    coll_name = os.getenv("MONGODB_KB_COLLECTION", "career_kb")
    index_name = os.getenv("MONGODB_VECTOR_INDEX", "career_vector_index")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        coll = client[db_name][coll_name]
        # Atlas $vectorSearch requires an embedding field populated server-side.
        # When the collection is empty or the index is missing, fall back quietly.
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": index_name,
                    "path": "embedding",
                    "queryVector": embed(career_goal),
                    "numCandidates": max(top_k * 10, 20),
                    "limit": top_k,
                }
            },
            {"$project": {
                "career": 1, "courses": 1, "target_categories": 1,
                "skills": 1, "score": {"$meta": "vectorSearchScore"},
            }},
        ]
        docs = list(coll.aggregate(pipeline))
        if not docs:
            return None
        return [
            RAGHit(
                career=d.get("career", ""),
                score=float(d.get("score", 0.0)),
                courses=tuple(d.get("courses", [])),
                target_categories=tuple(d.get("target_categories", [])),
                skills=tuple(d.get("skills", [])),
                source="mongodb",
            )
            for d in docs
        ]
    except Exception:
        return None


def retrieve_career_context(career_goal: str, top_k: int = 2) -> tuple[list[RAGHit], list[str], set[str]]:
    """Return (RAG hits, target categories, grounded course codes)."""

    hits = _mongo_retrieve(career_goal, top_k)
    if hits is None:
        # Local path: hybrid (BM25 + dense) fusion over the curated KB.
        hits = _hits_from_kb(hybrid_retrieve(career_goal, top_k), source="hybrid")

    categories: list[str] = []
    codes: set[str] = set()
    for h in hits:
        codes.update(h.courses)
        for cat in h.target_categories:
            if cat not in categories:
                categories.append(cat)
    return hits, categories, codes


def rag_backend() -> str:
    from data.embeddings import embedding_backend

    if os.getenv("MONGODB_URI"):
        if _mongo_retrieve("test", 1) is not None:
            return "mongodb vector search"
        return "mongodb (configured, hybrid fallback active)"
    return f"hybrid BM25+dense (local KB, {embedding_backend()} embeddings)"
