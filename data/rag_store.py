"""RAG retrieval: MongoDB Atlas Vector Search with offline fallback.

Career→course grounding must never invent codes. This module is the single
retrieval seam: vector DB when configured, else token-cosine over the curated KB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from data.knowledge_base import KBEntry, KNOWLEDGE_BASE, retrieve as kb_retrieve


@dataclass(frozen=True)
class RAGHit:
    career: str
    score: float
    courses: tuple[str, ...]
    target_categories: tuple[str, ...]
    skills: tuple[str, ...]
    source: str  # "mongodb" | "cosine"


def _hits_from_kb(scored: list[tuple[KBEntry, float]]) -> list[RAGHit]:
    return [
        RAGHit(
            career=e.career,
            score=round(s, 4),
            courses=tuple(e.courses),
            target_categories=tuple(e.target_categories),
            skills=tuple(e.skills),
            source="cosine",
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
                    "queryVector": _embed_query(career_goal),
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


def _embed_query(text: str) -> list[float]:
    """Embed a query for vector search. Uses OpenAI when configured, else a hash bag."""

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    if api_key:
        try:
            import httpx

            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": text, "model": model},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception:
            pass
    # Deterministic pseudo-embedding for local dev (not for production search quality).
    import hashlib
    import math

    dim = 64
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def retrieve_career_context(career_goal: str, top_k: int = 2) -> tuple[list[RAGHit], list[str], set[str]]:
    """Return (RAG hits, target categories, grounded course codes)."""

    hits = _mongo_retrieve(career_goal, top_k)
    if hits is None:
        hits = _hits_from_kb(kb_retrieve(career_goal, top_k))

    categories: list[str] = []
    codes: set[str] = set()
    for h in hits:
        codes.update(h.courses)
        for cat in h.target_categories:
            if cat not in categories:
                categories.append(cat)
    return hits, categories, codes


def rag_backend() -> str:
    if os.getenv("MONGODB_URI"):
        return "mongodb" if _mongo_retrieve("test", 1) is not None else "mongodb (configured, fallback active)"
    return "cosine (local KB)"
