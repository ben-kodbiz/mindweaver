"""Embedding provider interface.

Text encoders (local hashing, sentence-transformers, future remote APIs) are
all behind this interface so retrieval never depends on a specific model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    name: str
    model_name: str
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalised embedding vectors, one per input text."""
