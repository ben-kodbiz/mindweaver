"""Sentence-Transformers embedding provider (optional ``[embeddings]`` extra)."""

from __future__ import annotations

from mindweaver.search.embeddings.base import EmbeddingProvider


class SentenceTransformerProvider(EmbeddingProvider):
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        dimension = self._model.get_sentence_embedding_dimension()
        self.dimension = int(dimension or 0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        from typing import cast as _cast

        import numpy as np

        vectors = self._model.encode(texts, normalize_embeddings=True)
        return _cast(list[list[float]], np.asarray(vectors, dtype=float).tolist())
