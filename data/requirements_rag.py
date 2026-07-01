"""Retrieve program-requirement context from the live UW calendar (RAG).

For any program, fetch its subject's UW calendar page(s), chunk them, and return
the chunks most relevant to the question — so the LLM answers grounded in real
UW text instead of a hardcoded requirements table.
"""

from __future__ import annotations

from data.calendar import fetch_subject_courses, subjects_for_program
from data.chunking import chunk_documents
from data.embeddings import BM25, cosine, embed, embed_batch, tokenize


def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return fused


def retrieve_program_requirements(query: str, *, max_chunks: int = 6) -> tuple[str, list[str]]:
    """Return (grounding context, source URLs) for a program-requirements query."""

    subjects = subjects_for_program(query)
    documents: dict[str, str] = {}
    urls: list[str] = []
    for subject in subjects[:2]:  # cap live fetches per query
        fetched = fetch_subject_courses(subject)
        if fetched:
            text, url = fetched
            documents[url] = text
            urls.append(url)
    if not documents:
        return "", urls

    chunks = chunk_documents(documents, max_chars=600, overlap_chars=80)
    if not chunks:
        return "", urls

    order = list(range(len(chunks)))
    corpus = [tokenize(c.text) for c in chunks]
    sparse = BM25(corpus).scores(tokenize(query))
    qvec = embed(query)
    dense = [cosine(qvec, dv) for dv in embed_batch([c.text for c in chunks])]

    sparse_rank = sorted(order, key=lambda i: sparse[i], reverse=True)
    dense_rank = sorted(order, key=lambda i: dense[i], reverse=True)
    fused = _rrf([sparse_rank, dense_rank])
    top = sorted(fused, key=lambda i: fused[i], reverse=True)[:max_chunks]

    context = "\n\n".join(chunks[i].text for i in sorted(top))
    return context, urls
