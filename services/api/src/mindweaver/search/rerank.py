"""Reranker providers.

The reranker re-scores the merged candidate set. The initial local reranker
combines keyword and vector scores with a lexical-overlap boost; a
cross-encoder can be added later behind the same interface.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from mindweaver.config import Settings
from mindweaver.search.base import SearchHit

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


class Reranker(ABC):
    name: str

    @abstractmethod
    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        """Sort hits best-first, setting ``rerank_score`` on each."""


class LocalReranker(Reranker):
    """Weighted combination of keyword + vector scores with an overlap boost."""

    name = "local"

    def __init__(self, fts_weight: float = 0.4, vector_weight: float = 0.6) -> None:
        self._fts_weight = fts_weight
        self._vector_weight = vector_weight

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        query_tokens = _tokens(query)
        for hit in hits:
            overlap = 0.0
            if query_tokens:
                hit_tokens = _tokens(hit.text)
                overlap = len(query_tokens & hit_tokens) / len(query_tokens)
            hit.rerank_score = (
                self._fts_weight * (hit.keyword_score or 0.0)
                + self._vector_weight * (hit.vector_score or 0.0)
                + 0.05 * overlap
            )
        hits.sort(key=lambda hit: hit.rerank_score or 0.0, reverse=True)
        return hits


def get_reranker(settings: Settings) -> Reranker | None:
    if not settings.reranker.enabled:
        return None
    provider = (settings.reranker.provider or "").strip().lower()
    if provider in ("none", "disabled", ""):
        return None
    if provider == "local":
        return LocalReranker(
            fts_weight=settings.search.fts_weight,
            vector_weight=settings.search.vector_weight,
        )
    raise UnknownRerankerError(f"unknown reranker provider: {provider}")


class UnknownRerankerError(Exception):
    pass
