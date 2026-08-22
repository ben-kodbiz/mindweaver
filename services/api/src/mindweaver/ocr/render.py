"""Render PDF pages to images for OCR (pypdfium2; optional dependency)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def render_page(path: str | Path, page_number: int, scale: float = 2.5) -> bytes:
    """Render a single PDF page (1-based) to PNG bytes."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_number - 1]
        bitmap = page.render(scale=float(scale))
        buffer = BytesIO()
        bitmap.to_pil().convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()
