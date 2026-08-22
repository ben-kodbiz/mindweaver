"""Indexing: populate the FTS table and chunk embeddings for a document."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.embeddings.registry import get_embedding_provider
from mindweaver.search.fts import index_document
from mindweaver.search.vector import delete_embeddings, store_embedding

logger = logging.getLogger(__name__)


def index_document_chunks(
    session: Session,
    settings: Settings,
    document: Document,
    records: list[ChunkRecord],
) -> list[str]:
    """Index chunk records into FTS and (optionally) the vector store.

    Returns a list of indexing warnings. Embedding failures are non-fatal so
    keyword search keeps working.
    """
    warnings: list[str] = []
    if not records:
        return warnings

    index_document(session, records)

    provider = get_embedding_provider(settings)
    if provider is None:
        return warnings

    try:
        vectors = provider.embed([record.text for record in records])
        delete_embeddings(session, document.id, provider.model_name)
        for record, vector in zip(records, vectors, strict=True):
            store_embedding(
                session,
                chunk_id=record.chunk_id,
                document_id=document.id,
                model_name=provider.model_name,
                dimension=provider.dimension,
                vector=vector,
            )
        session.flush()
    except Exception as exc:
        message = f"embedding failed for {document.id}: {exc}"
        logger.warning(message)
        warnings.append(message)
    return warnings
