"""Embedding provider registry."""

from __future__ import annotations

from mindweaver.config import Settings
from mindweaver.search.embeddings.base import EmbeddingProvider


class UnknownEmbeddingProviderError(Exception):
    pass


def get_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    provider = (settings.embeddings.provider or "").strip().lower()
    if provider in ("none", "disabled", ""):
        return None

    if provider in ("local", "hashing"):
        from mindweaver.search.embeddings.hashing import HashingEmbeddingProvider

        return HashingEmbeddingProvider(dimension=settings.embeddings.dimension)

    if provider == "sentence-transformers":
        try:
            from mindweaver.search.embeddings.sentence_transformer import (
                SentenceTransformerProvider,
            )
        except ImportError as exc:
            raise UnknownEmbeddingProviderError(
                "sentence-transformers provider selected but the [embeddings] extra "
                "is not installed; install with `uv sync --project services/api --extra embeddings`"
            ) from exc
        return SentenceTransformerProvider(model_name=settings.embeddings.model)

    raise UnknownEmbeddingProviderError(f"unknown embedding provider: {provider}")
