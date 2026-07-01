"""Document chunking for RAG ingestion.

Splits long text (course descriptions, program pages, calendar entries) into
overlapping, retrieval-sized chunks. Sentence-aware so chunks don't cut a
sentence in half, with a character budget and configurable overlap — the same
knobs a production ingestion pipeline exposes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    index: int
    metadata: dict[str, str] = field(default_factory=dict)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]


def chunk_text(
    text: str,
    *,
    source: str = "",
    max_chars: int = 500,
    overlap_chars: int = 80,
    metadata: dict[str, str] | None = None,
) -> list[Chunk]:
    """Sentence-aware chunks of at most ``max_chars`` with ``overlap_chars`` carryover.

    Overlap keeps context across chunk boundaries so a fact split across two
    sentences is still retrievable. A single oversized sentence is hard-split.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap_chars = max(0, min(overlap_chars, max_chars - 1))
    text = (text or "").strip()
    if not text:
        return []

    sentences = split_sentences(text) or [text]
    chunks: list[str] = []
    cur = ""
    for sent in sentences:
        # Hard-split a sentence that alone exceeds the budget.
        while len(sent) > max_chars:
            if cur:
                chunks.append(cur.strip())
                cur = ""
            chunks.append(sent[:max_chars].strip())
            sent = sent[max_chars - overlap_chars:]
        if not cur:
            cur = sent
        elif len(cur) + 1 + len(sent) <= max_chars:
            cur = f"{cur} {sent}"
        else:
            chunks.append(cur.strip())
            tail = cur[-overlap_chars:] if overlap_chars else ""
            cur = f"{tail} {sent}".strip() if tail else sent
    if cur.strip():
        chunks.append(cur.strip())

    md = dict(metadata or {})
    return [Chunk(text=c, source=source, index=i, metadata=md) for i, c in enumerate(chunks)]


def chunk_documents(
    documents: dict[str, str],
    *,
    max_chars: int = 500,
    overlap_chars: int = 80,
) -> list[Chunk]:
    """Chunk a ``{source_id: text}`` map into a flat list of chunks."""

    out: list[Chunk] = []
    for source, text in documents.items():
        out.extend(chunk_text(text, source=source, max_chars=max_chars, overlap_chars=overlap_chars))
    return out
