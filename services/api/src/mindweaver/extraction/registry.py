"""Document processor registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.extraction.base import DocumentProcessor
from mindweaver.ocr.base import OCRProvider
from mindweaver.ocr.registry import UnknownOCRProviderError, get_ocr_provider

if TYPE_CHECKING:
    from mindweaver.ocr.pipeline import OCRPipeline


class UnknownProcessorError(Exception):
    pass


def get_processor(
    settings: Settings,
    *,
    session: Session | None = None,
    ocr_provider: OCRProvider | None = None,
    ocr_enabled: bool = True,
) -> DocumentProcessor:
    """Return the configured document processor.

    Backends:
    - ``pypdf``/``native``: text extraction only; scanned pages set
      ``requires_ocr`` (document becomes ``OCR_REQUIRED``).
    - ``hybrid``: pypdf extraction + OCR routing for scanned pages (needs the
      ``[ocr]`` or ``[docling]`` extra).
    - ``docling``: full Docling pipeline (optional ``[docling]`` extra).
    """
    backend = (settings.document_processor.backend or "").strip().lower()

    if backend in ("pypdf", "native"):
        from mindweaver.extraction.pypdf_processor import PyPdfProcessor

        return PyPdfProcessor(ocr_pipeline=None)

    if backend == "hybrid":
        if not ocr_enabled:
            raise UnknownProcessorError(
                "hybrid backend requires OCR; set DOCUMENT_PROCESSOR__OCR_ENABLED=true "
                "or use the pypdf backend"
            )
        from mindweaver.extraction.pypdf_processor import PyPdfProcessor

        pipeline = _build_ocr_pipeline(settings, session, ocr_provider)
        return PyPdfProcessor(ocr_pipeline=pipeline)

    if backend == "docling":
        try:
            from mindweaver.extraction.docling_processor import DoclingProcessor
        except ImportError as exc:
            raise UnknownProcessorError(
                "docling processor selected but docling is not installed; "
                "install with `uv sync --project services/api --extra docling`"
            ) from exc
        return DoclingProcessor()

    raise UnknownProcessorError(f"unknown document processor backend: {backend}")


def _build_ocr_pipeline(
    settings: Settings,
    session: Session | None,
    ocr_provider: OCRProvider | None,
) -> OCRPipeline:
    if ocr_provider is None:
        try:
            ocr_provider = get_ocr_provider(settings)
        except UnknownOCRProviderError as exc:
            raise UnknownProcessorError(
                f"hybrid backend selected but OCR is unavailable: {exc}"
            ) from exc
    if session is None:
        raise UnknownProcessorError("hybrid backend requires a database session for OCR cache")
    from mindweaver.ocr.pipeline import OCRPipeline

    return OCRPipeline(settings, ocr_provider, session)
