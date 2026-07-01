"""Course-knowledge ETL for the RAG layer.

Extract → Transform → Load pipeline that ingests course/program documents into a
chunked, embedded document store the retriever can search. This is the GenAI
ingestion path: raw text in, retrieval-ready vectors out.

    Extract   pull course descriptions (UW Open Data API, else bundled mock)
    Transform chunk each document and embed each chunk
    Load      write chunks + vectors to JSON (or MongoDB when configured)

Run: ``python -m scripts.etl_courses --out data/vector_store.json``
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from data.chunking import Chunk, chunk_text
from data.embeddings import embed_batch, embedding_backend

log = logging.getLogger("schedugoose.etl")


@dataclass
class ETLStats:
    documents: int
    chunks: int
    embedded: int
    embedding_backend: str
    seconds: float
    destination: str


# --------------------------------------------------------------------------- #
# Extract
# --------------------------------------------------------------------------- #
def extract_course_documents(start_term: dict | None = None) -> dict[str, str]:
    """Return ``{course_id: text}`` for every course we can describe."""

    from data.uw_api import fetch_courses, lookup_course

    docs: dict[str, str] = {}
    for course in fetch_courses(start_term=start_term):
        facts = lookup_course(course.course_id, start_term=start_term)
        desc = facts.get("description") or ""
        prereqs = ", ".join(course.prereqs) if course.prereqs else "none"
        cats = ", ".join(course.categories)
        docs[course.course_id] = (
            f"{course.course_id} — {course.title}. {desc} "
            f"Prerequisites: {prereqs}. Categories: {cats}."
        ).strip()
    return docs


# --------------------------------------------------------------------------- #
# Transform
# --------------------------------------------------------------------------- #
@dataclass
class EmbeddedChunk:
    id: str
    source: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


def transform(documents: dict[str, str], *, max_chars: int = 500, overlap: int = 80) -> list[EmbeddedChunk]:
    """Chunk every document and embed every chunk (batched)."""

    chunks: list[Chunk] = []
    for source, text in documents.items():
        chunks.extend(chunk_text(text, source=source, max_chars=max_chars, overlap_chars=overlap))
    vectors = embed_batch([c.text for c in chunks]) if chunks else []
    return [
        EmbeddedChunk(
            id=f"{c.source}#{c.index}",
            source=c.source,
            text=c.text,
            embedding=vec,
            metadata=c.metadata,
        )
        for c, vec in zip(chunks, vectors)
    ]


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def load_json(records: list[EmbeddedChunk], path: str) -> str:
    payload = [asdict(r) for r in records]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def load_mongo(records: list[EmbeddedChunk]) -> str | None:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        coll = client[os.getenv("MONGODB_DB", "schedugoose")]["course_chunks"]
        coll.delete_many({})
        if records:
            coll.insert_many([asdict(r) for r in records])
        return "mongodb"
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("Mongo load failed (%s); falling back to JSON", exc)
        return None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_pipeline(
    *,
    out_path: str = "data/vector_store.json",
    start_term: dict | None = None,
    to_mongo: bool = False,
) -> ETLStats:
    t0 = time.time()
    docs = extract_course_documents(start_term)
    log.info("extracted %d course documents", len(docs))
    records = transform(docs)
    log.info("transformed into %d embedded chunks (%s)", len(records), embedding_backend())

    dest = load_mongo(records) if to_mongo else None
    if dest is None:
        dest = load_json(records, out_path)
    log.info("loaded %d chunks -> %s", len(records), dest)

    return ETLStats(
        documents=len(docs),
        chunks=len(records),
        embedded=sum(1 for r in records if r.embedding),
        embedding_backend=embedding_backend(),
        seconds=round(time.time() - t0, 2),
        destination=dest,
    )
