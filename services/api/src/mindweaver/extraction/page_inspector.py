"""Per-page content inspection for native/scanned/mixed routing."""

from __future__ import annotations

import enum
from typing import Any

from pypdf import PdfReader


class PageContentType(enum.StrEnum):
    NATIVE = "native"  # has an extractable text layer
    SCANNED = "scanned"  # no text; image-only page -> needs OCR
    MIXED = "mixed"  # has text and embedded images
    EMPTY = "empty"  # neither text nor images


class PageInspection:
    def __init__(
        self,
        page_number: int,
        content_type: PageContentType,
        text_length: int,
        has_images: bool,
    ) -> None:
        self.page_number = page_number
        self.content_type = content_type
        self.text_length = text_length
        self.has_images = has_images


def inspect_page(page: Any, page_number: int) -> PageInspection:
    try:
        raw = page.extract_text() or ""
    except Exception:
        raw = ""
    has_text = bool(raw.strip())
    try:
        has_images = bool(list(page.images))
    except Exception:
        has_images = False

    if has_text and has_images:
        content_type = PageContentType.MIXED
    elif has_text:
        content_type = PageContentType.NATIVE
    elif has_images:
        content_type = PageContentType.SCANNED
    else:
        content_type = PageContentType.EMPTY

    return PageInspection(
        page_number=page_number,
        content_type=content_type,
        text_length=len(raw.strip()),
        has_images=has_images,
    )


def inspect_pages(reader: PdfReader) -> list[PageInspection]:
    return [
        inspect_page(page, page_number) for page_number, page in enumerate(reader.pages, start=1)
    ]
