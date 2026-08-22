"""OCR provider interface.

Every OCR engine (rapidocr, tesseract, future PaddleOCR) is behind this
interface so the document pipeline never depends on a specific engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OCRWord:
    text: str
    confidence: float
    box: tuple[float, ...] | None = None


@dataclass
class OCRPageResult:
    page_number: int
    text: str
    confidence: float | None = None
    words: list[OCRWord] = field(default_factory=list)
    low_confidence: bool = False


class OCRProvider(ABC):
    """Recognises text in a rendered page image."""

    name: str

    @abstractmethod
    def ocr_image(self, image: bytes, *, page_number: int, languages: list[str]) -> OCRPageResult:
        """OCR a rendered page (PNG bytes) into per-page text + confidence."""
