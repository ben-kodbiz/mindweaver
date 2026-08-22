"""Document library service.

Handles upload, duplicate detection, metadata extraction (page count),
listing, reprocessing, and deletion of original documents.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, BinaryIO, cast

from pypdf import PdfReader
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from mindweaver import storage
from mindweaver.config import DocumentProcessorConfig, Settings
from mindweaver.extraction.registry import get_processor
from mindweaver.models import (
    ChunkEmbedding,
    ChunkRecord,
    Document,
    DocumentStatus,
    DocumentVersion,
    JobStatus,
    JobType,
    ProcessingJob,
)
from mindweaver.models.document import utcnow

CHUNK_SIZE = 1024 * 1024
PDF_MAGIC = b"%PDF-"
_TITLE_FROM_FILENAME = re.compile(r"(.*)\.pdf$", re.IGNORECASE)
CANONICAL_FILE = "canonical.json"


class DuplicateDocumentError(Exception):
    def __init__(self, existing: Document):
        self.existing = existing


class EmptyFileError(Exception):
    pass


class InvalidPdfError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


def title_from_filename(filename: str) -> str:
    match = _TITLE_FROM_FILENAME.match(filename or "")
    if match:
        return match.group(1).strip() or filename
    return filename or "untitled"


def find_duplicate(session: Session, sha256: str) -> Document | None:
    return session.scalar(select(Document).where(Document.sha256 == sha256))


def get_document(session: Session, document_id: str) -> Document | None:
    return session.get(Document, document_id)


def list_documents(
    session: Session, *, limit: int = 100, offset: int = 0
) -> tuple[list[Document], int]:
    total = session.scalar(select(func.count()).select_from(Document)) or 0
    documents = session.scalars(
        select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(documents), total


def upload_pdf(
    session: Session,
    settings: Settings,
    *,
    filename: str,
    file: BinaryIO,
) -> Document:
    """Stream an uploaded PDF into storage, deduplicate, and extract metadata.

    Raises :class:`EmptyFileError`, :class:`InvalidPdfError`,
    :class:`FileTooLargeError`, or :class:`DuplicateDocumentError`.
    """
    originals = settings.storage.originals_dir
    originals.mkdir(parents=True, exist_ok=True)
    temp_path = originals / f".upload-{uuid.uuid4().hex}"

    hasher = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("wb") as out:
            first = file.read(len(PDF_MAGIC))
            if not first:
                raise EmptyFileError("uploaded file is empty")
            if not first.startswith(PDF_MAGIC):
                raise InvalidPdfError("uploaded file is not a PDF")
            hasher.update(first)
            size += len(first)
            out.write(first)
            while chunk := file.read(CHUNK_SIZE):
                hasher.update(chunk)
                size += len(chunk)
                if size > settings.storage.max_upload_bytes:
                    raise FileTooLargeError(
                        f"file exceeds the {settings.storage.max_upload_bytes} byte limit"
                    )
                out.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    sha256 = hasher.hexdigest()
    duplicate = find_duplicate(session, sha256)
    if duplicate:
        temp_path.unlink(missing_ok=True)
        raise DuplicateDocumentError(duplicate)

    document = Document(
        title=title_from_filename(filename),
        original_filename=filename,
        sha256=sha256,
        file_size=size,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    session.flush()

    storage_key = f"{document.id}.pdf"
    temp_path.rename(originals / storage_key)

    version = DocumentVersion(
        document_id=document.id,
        version=1,
        sha256=sha256,
        file_size=size,
        storage_key=storage_key,
    )
    session.add(version)
    session.flush()

    job = ProcessingJob(
        document_id=document.id,
        job_type=JobType.METADATA_EXTRACTION,
        status=JobStatus.QUEUED,
    )
    session.add(job)
    session.flush()

    run_metadata_extraction(session, settings, document)
    session.flush()
    run_document_extraction(session, settings, document)
    session.flush()
    _chunk_if_usable(session, settings, document)
    session.flush()
    return document


def _chunk_if_usable(session: Session, settings: Settings, document: Document) -> None:
    """Chunk and graph the canonical content when extraction produced usable output."""
    if document.status not in (DocumentStatus.READY, DocumentStatus.OCR_REQUIRED):
        return
    from mindweaver.chunking.service import run_chunking

    run_chunking(session, settings, document)
    from mindweaver.graph.service import run_graph_extraction

    run_graph_extraction(session, settings, document)


def run_document_extraction(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    ocr_enabled: bool = True,
    job_type: JobType = JobType.DOCUMENT_EXTRACTION,
) -> None:
    """Run the configured document processor and persist the canonical model.

    Drives ``PROCESSING -> READY | OCR_REQUIRED | FAILED`` and stores the
    canonical JSON under the derived storage dir for the document.
    """
    job = ProcessingJob(
        document_id=document.id,
        job_type=job_type,
        status=JobStatus.RUNNING,
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()

    document.status = DocumentStatus.PROCESSING
    document.error_message = None

    version = document.versions[-1]
    path = storage.original_path(settings, version.storage_key)
    try:
        processor = get_processor(settings, session=session, ocr_enabled=ocr_enabled)
        result = processor.extract(
            path, document_id=document.id, filename=document.original_filename
        )
        document.page_count = len(result.document.pages) or None
        storage.save_derived_json(
            settings,
            document.id,
            CANONICAL_FILE,
            result.document.model_dump_json(indent=2),
        )
        if result.requires_ocr:
            document.status = DocumentStatus.OCR_REQUIRED
            document.error_message = (
                "OCR required for scanned page(s); reprocess with OCR to complete extraction"
            )
        else:
            document.status = DocumentStatus.READY
            document.error_message = None
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.completed_at = utcnow()
    except Exception as exc:
        document.status = DocumentStatus.FAILED
        document.error_message = str(exc)
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = utcnow()


def load_canonical_document(settings: Settings, document: Document) -> dict[str, Any] | None:
    raw = storage.load_derived_json(settings, document.id, CANONICAL_FILE)
    if raw is None:
        return None
    return cast(dict[str, Any], json.loads(raw))


def chunk_source_regions(
    session: Session, settings: Settings, document: Document, chunk_id: str
) -> dict[str, Any] | None:
    """Return the source regions (page + optional bbox + text) for a chunk."""
    from mindweaver.chunking.service import list_chunks

    chunk = next(
        (item for item in list_chunks(session, document.id) if item.chunk_id == chunk_id),
        None,
    )
    if chunk is None:
        return None

    canonical = load_canonical_document(settings, document)
    if canonical is None:
        return {"chunk_id": chunk_id, "regions": []}

    try:
        chunk_path = json.loads(chunk.section_path)
    except Exception:
        chunk_path = []
    page_set = set(range(chunk.page_start, chunk.page_end + 1))

    regions: list[dict[str, Any]] = []
    for block in canonical.get("blocks", []):
        if block.get("page_number") not in page_set:
            continue
        if block.get("section_path") != chunk_path:
            continue
        region: dict[str, Any] = {
            "page_number": block["page_number"],
            "text": block.get("text", ""),
        }
        bbox = block.get("bbox")
        if bbox:
            region["bbox"] = bbox
        regions.append(region)
    return {"chunk_id": chunk_id, "regions": regions}


def run_metadata_extraction(
    session: Session,
    settings: Settings,
    document: Document,
) -> None:
    """Read page count and PDF title; drive document/job status transitions.

    This is the lightweight Stage-2 "processing step". Full extraction is
    Stage 3+; the job/status model stays the same.
    """
    job = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document.id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    ).first()
    if job is None:
        job = ProcessingJob(document_id=document.id, job_type=JobType.METADATA_EXTRACTION)
        session.add(job)
        session.flush()

    document.status = DocumentStatus.QUEUED
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()

    version = document.versions[-1]
    path = storage.original_path(settings, version.storage_key)
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            raise ValueError("password-protected PDFs are not supported yet")
        document.page_count = len(reader.pages)
        metadata_title = getattr(reader.metadata, "title", None)
        if metadata_title:
            document.title = metadata_title.strip()
        document.status = DocumentStatus.READY
        document.error_message = None
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.error_message = None
        job.completed_at = utcnow()
    except Exception as exc:
        document.status = DocumentStatus.FAILED
        document.error_message = str(exc)
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = utcnow()


def reprocess_document(session: Session, settings: Settings, document: Document) -> Document:
    document.status = DocumentStatus.UPLOADED
    document.error_message = None
    job = ProcessingJob(
        document_id=document.id, job_type=JobType.METADATA_EXTRACTION, status=JobStatus.QUEUED
    )
    session.add(job)
    session.flush()
    run_metadata_extraction(session, settings, document)
    session.flush()
    run_document_extraction(session, settings, document)
    session.flush()
    _chunk_if_usable(session, settings, document)
    session.flush()
    return document


def reprocess_with_ocr(session: Session, settings: Settings, document: Document) -> Document:
    """Re-run extraction with the hybrid (OCR) backend.

    Uses the cached OCR results when available; pass ``force=True`` to ignore
    them (not wired to an API flag yet). OCR processing is per page and cached.
    """
    document.status = DocumentStatus.PROCESSING_OCR
    document.error_message = None
    ocr_settings = settings.model_copy(
        update={
            "document_processor": DocumentProcessorConfig(
                backend="hybrid",
                ocr_enabled=True,
            )
        }
    )
    run_document_extraction(session, ocr_settings, document, ocr_enabled=True, job_type=JobType.OCR)
    session.flush()
    _chunk_if_usable(session, settings, document)
    session.flush()
    return document


def delete_document(session: Session, settings: Settings, document: Document) -> None:
    for version in document.versions:
        storage.delete_original(settings, version.storage_key)
    storage.delete_derived(settings, document.id)
    session.query(ChunkRecord).filter(ChunkRecord.document_id == document.id).delete(
        synchronize_session=False
    )
    session.query(ChunkEmbedding).filter(ChunkEmbedding.document_id == document.id).delete(
        synchronize_session=False
    )
    session.execute(
        text("DELETE FROM chunks_fts WHERE document_id = :document_id"),
        {"document_id": document.id},
    )
    session.delete(document)
