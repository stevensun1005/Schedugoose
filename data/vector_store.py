"""Semantic course search over the ETL vector store.

Consumes the store produced by ``scripts/etl_courses.py`` (chunked, embedded
course docs). If that file isn't present, it builds an in-memory index from the
catalog on first use, so search works with or without a prior ETL run.
"""

from __future__ import annotations

import json
import os

from data.embeddings import cosine, embed, tokenize


def _stem(tokens: list[str]) -> set[str]:
    """Very light stemming so 'databases' matches 'database'."""

    return {t[:-1] if len(t) > 4 and t.endswith("s") else t for t in tokens}

_STORE: list[tuple[str, str, list[float]]] | None = None  # (course_id, text, embedding)


def _build_from_catalog() -> list[tuple[str, str, list[float]]]:
    from data.chunking import chunk_documents
    from data.embeddings import embed_batch
    from data.uw_api import fetch_courses

    docs = {
        c.course_id: f"{c.course_id} — {c.title}. Categories: {', '.join(c.categories)}. "
        f"Prerequisites: {', '.join(c.prereqs) or 'none'}."
        for c in fetch_courses()
    }
    chunks = chunk_documents(docs, max_chars=300, overlap_chars=0)
    vectors = embed_batch([c.text for c in chunks])
    return [(c.source, c.text, v) for c, v in zip(chunks, vectors)]


def _store() -> list[tuple[str, str, list[float]]]:
    global _STORE
    if _STORE is not None:
        return _STORE
    path = os.getenv("VECTOR_STORE", "data/vector_store.json")
    if os.path.exists(path):
        try:
            records = json.load(open(path, encoding="utf-8"))
            _STORE = [(r["source"], r["text"], r["embedding"]) for r in records]
            return _STORE
        except Exception:
            pass
    _STORE = _build_from_catalog()
    return _STORE


def reset() -> None:
    global _STORE
    _STORE = None


def search(query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
    """Return up to ``top_k`` (course_id, text, score) most similar to the query.

    Hybrid: dense embedding similarity + a light-stemmed lexical overlap, so it
    stays useful even with the local (non-semantic) fallback embeddings.
    """

    qvec = embed(query)
    qterms = _stem(tokenize(query)) - {"and", "or", "the", "for", "about", "course", "courses"}
    scored = []
    for src, text, emb in _store():
        dense = cosine(qvec, emb)
        doc_terms = _stem(tokenize(text))
        lexical = len(qterms & doc_terms) / len(qterms) if qterms else 0.0
        scored.append((src, text, dense + 0.6 * lexical))
    scored.sort(key=lambda t: t[2], reverse=True)
    out: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    for src, text, score in scored:
        if src in seen:
            continue
        seen.add(src)
        out.append((src, text, round(score, 3)))
        if len(out) >= top_k:
            break
    return out
