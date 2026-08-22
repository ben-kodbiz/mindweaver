"""Vector store for chunk embeddings.

Vectors are stored as raw float32 blobs in SQLite and searched with a
brute-force cosine similarity pass. This is intentionally simple for a
local-first corpus (thousands of chunks); swap for an ANN index later if it
becomes a bottleneck.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver.models import ChunkEmbedding


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def delete_embeddings(session: Session, document_id: str, model_name: str) -> None:
    session.query(ChunkEmbedding).filter(
        ChunkEmbedding.document_id == document_id,
        ChunkEmbedding.model_name == model_name,
    ).delete(synchronize_session=False)


def store_embedding(
    session: Session,
    *,
    chunk_id: str,
    document_id: str,
    model_name: str,
    dimension: int,
    vector: list[float],
) -> None:
    session.add(
        ChunkEmbedding(
            chunk_id=chunk_id,
            document_id=document_id,
            model_name=model_name,
            dimension=dimension,
            vector=_pack(vector),
        )
    )


def vector_search(
    session: Session,
    query_vector: list[float],
    model_name: str,
    *,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return top-k ``{chunk_id, score}`` by cosine similarity."""
    statement = select(ChunkEmbedding).where(ChunkEmbedding.model_name == model_name)
    if document_ids:
        statement = statement.where(ChunkEmbedding.document_id.in_(document_ids))
    elif document_id is not None:
        statement = statement.where(ChunkEmbedding.document_id == document_id)

    query = np.asarray(query_vector, dtype=np.float32)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return []
    query = query / query_norm

    scored: list[tuple[float, str]] = []
    for row in session.scalars(statement).all():
        vector = _unpack(row.vector)
        norm = np.linalg.norm(vector)
        if norm == 0:
            continue
        similarity = float(np.dot(query, vector / norm))
        scored.append((similarity, row.chunk_id))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [{"chunk_id": chunk_id, "score": score} for score, chunk_id in scored[:limit]]
