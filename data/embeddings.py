"""Embeddings + lexical scoring primitives for retrieval.

Two retrieval signals that a hybrid RAG pipeline fuses:
- **Dense** — vector embeddings (OpenAI when ``OPENAI_API_KEY`` is set, else a
  deterministic local hash embedding so dev/CI runs offline).
- **Sparse** — BM25 lexical scoring over tokenized text.

Kept dependency-free (no numpy) so the core runs anywhere.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from typing import Sequence

_TOKEN = re.compile(r"[a-z0-9]+")
_EMBED_DIM = 256


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


# --------------------------------------------------------------------------- #
# Dense embeddings
# --------------------------------------------------------------------------- #
def _local_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Deterministic hashing embedding — offline stand-in, L2-normalized."""

    vec = [0.0] * dim
    for tok in tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5  # a second bucket reduces collisions
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    return embed_batch([text])[0]


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """Embed many texts. Uses OpenAI embeddings when configured, else local."""

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and texts:
        model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
        try:
            import httpx

            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": list(texts), "model": model},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except Exception:
            pass
    return [_local_embed(t) for t in texts]


def embedding_backend() -> str:
    return "openai" if os.getenv("OPENAI_API_KEY") else "local-hash"


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------------------- #
# Sparse lexical scoring (BM25)
# --------------------------------------------------------------------------- #
class BM25:
    """Minimal BM25 over a fixed corpus of pre-tokenized documents."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.doc_len = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_len) / len(corpus)) if corpus else 0.0
        self.freqs = [Counter(d) for d in corpus]
        df: Counter[str] = Counter()
        for d in corpus:
            df.update(set(d))
        n = len(corpus)
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query: list[str], index: int) -> float:
        freqs = self.freqs[index]
        dl = self.doc_len[index] or 1
        total = 0.0
        for term in query:
            if term not in freqs:
                continue
            idf = self.idf.get(term, 0.0)
            tf = freqs[term]
            denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            total += idf * (tf * (self.k1 + 1)) / (denom or 1)
        return total

    def scores(self, query: list[str]) -> list[float]:
        return [self.score(query, i) for i in range(len(self.corpus))]
