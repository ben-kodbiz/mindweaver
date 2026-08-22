"""OCR result caching.

OCR output for a (document, page, provider, languages) key is stored in
SQLite so reprocessing is fast and does not re-run the engine for pages
already recognised.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver.models import OcrCache
from mindweaver.ocr.base import OCRPageResult, OCRWord


def cache_key(document_id: str, page_number: int, provider: str, languages: list[str]) -> str:
    return ",".join(sorted(languages))


def get_cached_ocr(
    session: Session,
    document_id: str,
    page_number: int,
    provider: str,
    languages: list[str],
) -> OCRPageResult | None:
    record = session.scalar(
        select(OcrCache).where(
            OcrCache.document_id == document_id,
            OcrCache.page_number == page_number,
            OcrCache.provider == provider,
            OcrCache.languages == cache_key(document_id, page_number, provider, languages),
        )
    )
    if record is None:
        return None
    words = [
        OCRWord(text=word["text"], confidence=word["confidence"])
        for word in json.loads(record.words_json)
    ]
    return OCRPageResult(
        page_number=page_number,
        text=record.text,
        confidence=record.confidence,
        words=words,
        low_confidence=record.low_confidence,
    )


def store_cached_ocr(
    session: Session,
    document_id: str,
    page_number: int,
    provider: str,
    languages: list[str],
    result: OCRPageResult,
) -> None:
    record = OcrCache(
        document_id=document_id,
        page_number=page_number,
        provider=provider,
        languages=cache_key(document_id, page_number, provider, languages),
        text=result.text,
        confidence=result.confidence,
        words_json=json.dumps(
            [{"text": word.text, "confidence": word.confidence} for word in result.words]
        ),
        low_confidence=result.low_confidence,
    )
    session.add(record)
