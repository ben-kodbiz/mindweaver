"""OCR provider registry."""

from __future__ import annotations

from mindweaver.config import Settings
from mindweaver.ocr.base import OCRProvider


class UnknownOCRProviderError(Exception):
    pass


def get_ocr_provider(settings: Settings) -> OCRProvider:
    provider = (settings.ocr.provider or "").strip().lower()
    if provider in ("none", "disabled"):
        raise UnknownOCRProviderError("OCR is disabled")

    if provider == "rapidocr":
        try:
            from mindweaver.ocr.rapidocr_provider import RapidOCRProvider
        except ImportError as exc:
            raise UnknownOCRProviderError(
                "rapidocr provider selected but OCR deps are not installed; "
                "install with `uv sync --project services/api --extra ocr` "
                "(or --extra docling)"
            ) from exc
        return RapidOCRProvider(settings)

    raise UnknownOCRProviderError(f"unknown OCR provider: {provider}")
