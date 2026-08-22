"""Local embedding provider: feature-hashed bag-of-words vectors.

Deterministic, corpus-independent, and needs no model download. Useful as the
default for weak hardware; swap to a real model via
``EMBEDDINGS__PROVIDER=sentence-transformers``.
"""

from __future__ import annotations

import hashlib
import math
import re

from mindweaver.search.embeddings.base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class HashingEmbeddingProvider(EmbeddingProvider):
    name = "local"

    def __init__(self, dimension: int = 512) -> None:
        self.model_name = f"hashing-bow-{dimension}"
        self.dimension = int(dimension)

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in _tokens(text):
                digest = hashlib.md5(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            if norm > 0:
                vector = [value / norm for value in vector]
            results.append(vector)
        return results
