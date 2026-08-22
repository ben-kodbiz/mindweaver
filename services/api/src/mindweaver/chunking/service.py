"""Chunking pipeline service: canonical document -> stored chunks."""

from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mindweaver import storage
from mindweaver.chunking.model import Chunk
from mindweaver.chunking.structural import chunk_document
from mindweaver.config import Settings
from mindweaver.document_model import CanonicalDocument
from mindweaver.models import (
    ChunkRecord,
    Document,
    DocumentStatus,
    JobStatus,
    JobType,
    ProcessingJob,
)
from mindweaver.models.document import utcnow


def load_canonical_document(settings: Settings, document_id: str) -> CanonicalDocument | None:
    raw = storage.load_derived_json(settings, document_id, "canonical.json")
    if raw is None:
        return None
    return CanonicalDocument.model_validate_json(raw)


def chunk_document_from_storage(
    session: Session, settings: Settings, document: Document
) -> list[Chunk]:
    canonical = load_canonical_document(settings, document.id)
    if canonical is None:
        return []
    return chunk_document(
        canonical,
        max_chars=settings.chunking.max_chars,
        min_chars=settings.chunking.min_chars,
    )


def run_chunking(session: Session, settings: Settings, document: Document) -> list[Chunk]:
    """Chunk the stored canonical document and replace the stored chunks.

    Creates a ``chunking`` job; on failure marks the document ``FAILED``.
    """
    job = ProcessingJob(
        document_id=document.id,
        job_type=JobType.CHUNKING,
        status=JobStatus.RUNNING,
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()

    try:
        chunks = chunk_document_from_storage(session, settings, document)
        session.execute(delete(ChunkRecord).where(ChunkRecord.document_id == document.id))
        for position, chunk in enumerate(chunks):
            session.add(
                ChunkRecord(
                    chunk_id=chunk.chunk_id,
                    document_id=document.id,
                    position=position,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    subsection=chunk.subsection,
                    section_path=json.dumps(chunk.section_path),
                    text=chunk.text,
                    token_count=chunk.token_count,
                    parent_chunk_id=chunk.parent_chunk_id,
                )
            )
        session.flush()
        from mindweaver.search.indexing import index_document_chunks

        records = list_chunks(session, document.id)
        index_document_chunks(session, settings, document, records)
        session.flush()
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.completed_at = utcnow()
        return chunks
    except Exception as exc:
        document.status = DocumentStatus.FAILED
        document.error_message = f"chunking failed: {exc}"
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = utcnow()
        raise


def list_chunks(session: Session, document_id: str) -> list[ChunkRecord]:
    return list(
        session.scalars(
            select(ChunkRecord)
            .where(ChunkRecord.document_id == document_id)
            .order_by(ChunkRecord.position)
        ).all()
    )


def chunk_record_to_model(record: ChunkRecord) -> Chunk:
    return Chunk(
        chunk_id=record.chunk_id,
        document_id=record.document_id,
        page_start=record.page_start,
        page_end=record.page_end,
        chapter=record.chapter,
        section=record.section,
        subsection=record.subsection,
        section_path=json.loads(record.section_path),
        text=record.text,
        token_count=record.token_count,
        parent_chunk_id=record.parent_chunk_id,
    )
