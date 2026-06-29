"""Career -> skills -> courses knowledge base (RAG grounding).

Career->courses is RAG-grounded, never free-form: the LLM is never allowed to
invent course codes. We retrieve real course codes from this curated KB and let
relevance scoring run *only within* the codes that came back.

Retrieval here is an embedding-free token-cosine fallback so the system runs
with zero external services. The interface (:func:`retrieve`) is the seam where
a real vector store / embedding model would drop in.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from scheduler.types import Course


@dataclass
class KBEntry:
    career: str
    aliases: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    courses: list[str] = field(default_factory=list)
    target_categories: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join([self.career, *self.aliases, *self.skills]).lower()


# Curated, owned knowledge base.
KNOWLEDGE_BASE: list[KBEntry] = [
    KBEntry(
        career="data scientist",
        aliases=["data science", "ml engineer", "machine learning engineer", "analytics"],
        skills=["statistical inference", "machine learning", "data wrangling",
                "sql", "databases", "probability", "computational statistics"],
        courses=["STAT 231", "STAT 341", "CS 486", "CS 480", "CS 451", "CS 348"],
        target_categories=["CS-AI", "STAT-ML"],
    ),
    KBEntry(
        career="ai researcher",
        aliases=["artificial intelligence", "deep learning", "research scientist"],
        skills=["machine learning", "logic", "search", "probabilistic reasoning",
                "optimization", "neural networks"],
        courses=["CS 486", "CS 480", "CS 245", "STAT 341"],
        target_categories=["CS-AI", "CS-Theory"],
    ),
    KBEntry(
        career="backend engineer",
        aliases=["software engineer", "systems developer", "distributed systems"],
        skills=["databases", "distributed computing", "algorithms", "systems"],
        courses=["CS 348", "CS 451", "CS 341", "CS 240"],
        target_categories=["CS-Systems", "CS-Theory"],
    ),
    KBEntry(
        career="security engineer",
        aliases=["cryptography", "cybersecurity", "appsec"],
        skills=["cryptography", "security", "number theory", "logic"],
        courses=["CO 487", "CS 245", "CS 341"],
        target_categories=["CS-Security", "CS-Theory"],
    ),
]

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _bag(tokens: list[str]) -> dict[str, int]:
    bag: dict[str, int] = {}
    for t in tokens:
        bag[t] = bag.get(t, 0) + 1
    return bag


def _cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(career_goal: str, top_k: int = 2) -> list[tuple[KBEntry, float]]:
    """Return the top-k KB entries most similar to the career goal, with scores."""

    query = _bag(_tokenize(career_goal))
    scored = [(e, _cosine(query, _bag(_tokenize(e.text)))) for e in KNOWLEDGE_BASE]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    matched = [pair for pair in scored if pair[1] > 0][:top_k]
    # Always fall back to the single best entry if nothing scored.
    return matched or scored[:1]


def ground(career_goal: str, top_k: int = 2) -> tuple[set[str], list[str]]:
    """Return (real course codes, target categories) grounded in the KB.

    These are the *only* course codes the relevance layer is allowed to favour.
    """

    course_ids: set[str] = set()
    categories: list[str] = []
    for entry, _ in retrieve(career_goal, top_k):
        course_ids.update(entry.courses)
        for cat in entry.target_categories:
            if cat not in categories:
                categories.append(cat)
    return course_ids, categories


def score_courses(courses: list[Course], career_goal: str, top_k: int = 2) -> list[str]:
    """Annotate ``career_relevance`` on each course in place; return categories.

    Scoring is grounded: a course listed in the KB for this career scores high;
    a course merely in a target category scores medium; everything else low.
    """

    grounded_ids, categories = ground(career_goal, top_k)
    cat_set = set(categories)
    for c in courses:
        if c.course_id in grounded_ids:
            c.career_relevance = 1.0
        elif cat_set & set(c.categories):
            c.career_relevance = 0.6
        else:
            c.career_relevance = 0.1
    return categories
