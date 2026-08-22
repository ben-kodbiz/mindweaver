"""OCR orchestration: render, cache, and provider calls."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.ocr.base import OCRPageResult, OCRProvider
from mindweaver.ocr.cache import get_cached_ocr, store_cached_ocr
from mindweaver.ocr.render import render_page


class OCRPipeline:
    """Runs OCR for a page: cache lookup -> render -> provider -> cache store."""

    def __init__(self, settings: Settings, provider: OCRProvider, session: Session) -> None:
        self._settings = settings
        self._provider = provider
        self._session = session

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def ocr_page(
        self, path: Path, document_id: str, page_number: int, *, force: bool = False
    ) -> OCRPageResult:
        languages = list(self._settings.ocr.languages)
        if not force:
            cached = get_cached_ocr(
                self._session,
                document_id,
                page_number,
                self._provider.name,
                languages,
            )
            if cached is not None:
                return cached

        image = render_page(path, page_number, scale=self._settings.ocr.render_scale)
        result = self._provider.ocr_image(image, page_number=page_number, languages=languages)
        store_cached_ocr(
            self._session,
            document_id,
            page_number,
            self._provider.name,
            languages,
            result,
        )
        return result
