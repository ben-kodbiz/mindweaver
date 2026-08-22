"""Render PDF pages to images for OCR (pypdfium2; optional dependency)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def render_page(
    path: str | Path, page_number: int, scale: float = 2.5, max_side: int = 2400
) -> bytes:
    """Render a single PDF page (1-based) to PNG bytes.

    The effective scale is reduced for very large pages so the rendered image
    never exceeds ``max_side`` pixels on its longest side (keeps OCR stable).
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_number - 1]
        width, height = page.get_size()
        capped = min(float(scale), max_side / max(width, height))
        bitmap = page.render(scale=max(0.4, capped))
        buffer = BytesIO()
        bitmap.to_pil().convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()
