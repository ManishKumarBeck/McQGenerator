"""Hybrid retrieval: BM25 keyword scoring + embedding similarity, fused and diversified.

Two modes:
* focused   - the user gave a topic/chapter/keywords: return the most relevant passages;
* coverage  - no focus: sample passages spread evenly across the whole document(s).
"""

import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ...errors import InvalidInputError

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "more",
        "most",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "so",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "about",
        "above",
        "after",
        "again",
        "all",
        "also",
        "any",
        "because",
        "before",
        "being",
        "below",
        "between",
        "both",
        "during",
        "each",
        "few",
        "further",
        "here",
        "just",
        "only",
        "other",
        "over",
        "own",
        "same",
        "some",
        "very",
        "chapter",
        "section",
        "page",
    ]
)
RRF_K = 60


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in _WORD.findall(text.lower()):
        if len(word) < 2 or word in STOPWORDS:
            continue
        # Very light stemming so "cells" matches "cell" and "dividing" matches "divide".
        for suffix in ("ing", "es", "ed", "s"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        tokens.append(word)
    return tokens


@dataclass
class Passage:
    """A chunk available for retrieval (decoupled from the ORM for easy testing)."""

    key: tuple[int, int]  # (source_id, position)
    text: str
    citation: str
    embedding: np.ndarray | None = None
    tokens: list[str] = field(default_factory=list)


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(doc) for doc in documents]
        self.lengths = [len(doc) for doc in documents]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        frequency: Counter[str] = Counter()
        for doc in self.docs:
            frequency.update(doc.keys())
        n = len(documents)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        result = np.zeros(len(self.docs), dtype=np.float32)
        terms = [t for t in set(query) if t in self.idf]
        for i, doc in enumerate(self.docs):
            length_norm = 1 - self.b + self.b * (self.lengths[i] / self.avg_length if self.avg_length else 0)
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if tf:
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * length_norm)
            result[i] = score
        return result


def _ranks(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=np.int64)
    ranks[order] = np.arange(len(scores))
    return ranks


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def _fill_budget(candidates: list[Passage], budget: int, max_passages: int) -> list[Passage]:
    chosen, used = [], 0
    for passage in candidates:
        if chosen and used + len(passage.text) > budget:
            continue
        chosen.append(passage)
        used += len(passage.text)
        if used >= budget or len(chosen) >= max_passages:
            break
    return chosen


@dataclass
class SearchHit:
    passage: Passage
    score: float
    keyword_score: float
    semantic_score: float | None


def rank(passages: list[Passage], query: str, query_embedding: np.ndarray | None) -> list[SearchHit]:
    """Rank passages for a query using reciprocal-rank fusion of BM25 and cosine similarity."""
    query_tokens = tokenize(query)
    for passage in passages:
        if not passage.tokens:
            passage.tokens = tokenize(passage.text)
    keyword = BM25([p.tokens for p in passages]).scores(query_tokens)

    semantic = None
    if query_embedding is not None and passages and all(p.embedding is not None for p in passages):
        matrix = np.vstack([p.embedding for p in passages])
        semantic = matrix @ query_embedding

    fused = 1.0 / (RRF_K + _ranks(keyword) + 1)
    if semantic is not None:
        fused = fused + 1.0 / (RRF_K + _ranks(semantic) + 1)
    else:
        # Keyword-only: passages with zero keyword overlap are not relevant at all.
        fused = np.where(keyword > 0, fused, 0.0)

    order = np.argsort(-fused, kind="stable")
    return [
        SearchHit(
            passage=passages[i],
            score=float(fused[i]),
            keyword_score=float(keyword[i]),
            semantic_score=float(semantic[i]) if semantic is not None else None,
        )
        for i in order
        if fused[i] > 0
    ]


def _diversify(hits: list[SearchHit], limit: int, lambda_: float = 0.7) -> list[Passage]:
    """Maximal marginal relevance: prefer relevant passages that aren't near-duplicates."""
    pool = hits[: max(limit * 3, 12)]
    if not pool:
        return []
    max_score = pool[0].score or 1.0
    selected: list[SearchHit] = []
    while pool and len(selected) < limit:
        best, best_value = None, -math.inf
        for hit in pool:
            if hit.passage.embedding is not None and selected and selected[0].passage.embedding is not None:
                similarity = max(float(hit.passage.embedding @ s.passage.embedding) for s in selected)
            else:
                similarity = max(
                    (_jaccard(hit.passage.tokens, s.passage.tokens) for s in selected), default=0.0
                )
            value = lambda_ * (hit.score / max_score) - (1 - lambda_) * similarity
            if value > best_value:
                best, best_value = hit, value
        selected.append(best)
        pool.remove(best)
    return [hit.passage for hit in selected]


def _looks_like_content(text: str) -> bool:
    """Skip tables of contents, indexes and reference lists when sampling for coverage."""
    if len(text) < 300:
        return False
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    return letters / len(text) > 0.55 and digits / len(text) < 0.12


def select_passages(
    passages: list[Passage],
    *,
    query: str | None,
    query_embedding: np.ndarray | None,
    budget_chars: int,
    rng: random.Random | None = None,
    max_passages: int = 40,
) -> list[Passage]:
    """Pick passages to send to the question generator, within a character budget."""
    if not passages:
        raise InvalidInputError("The selected sources have no indexed text yet.")
    rng = rng or random.Random()
    average = max(1, sum(len(p.text) for p in passages) // len(passages))
    wanted = max(1, min(max_passages, budget_chars // average))

    if query and query.strip():
        hits = rank(passages, query, query_embedding)
        if not hits:
            raise InvalidInputError(
                f"Nothing in the selected sources matches “{query.strip()}”. "
                "Try different keywords, or leave the focus empty to use the whole source."
            )
        chosen = _fill_budget(_diversify(hits, wanted), budget_chars, max_passages)
    else:
        eligible = [p for p in passages if _looks_like_content(p.text)] or passages
        if len(eligible) <= wanted:
            sample = eligible
        else:
            # One random passage from each of `wanted` equal slices => even coverage, varied per run.
            step = len(eligible) / wanted
            sample = [
                eligible[min(len(eligible) - 1, int(i * step + rng.random() * step))] for i in range(wanted)
            ]
        chosen = _fill_budget(sample, budget_chars, max_passages)
    return sorted(chosen, key=lambda p: p.key)
