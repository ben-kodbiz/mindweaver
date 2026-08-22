"""Programmatic PDF fixtures (no binaries committed to the repo).

Uses reportlab (dev dependency) to build realistic PDFs with headings,
paragraphs, tables, figures, footnotes, columns, and multilingual text,
then pypdf to add outline bookmarks.
"""

from __future__ import annotations

import re
import struct
import zlib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_DEJAVU_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_ARABIC_FONT = "/usr/share/fonts/truetype/noto/NotoSansArabicUI-Regular.ttf"

_FONT_REGISTERED = False


def _register_fonts() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    if Path(_DEJAVU_SANS).exists():
        pdfmetrics.registerFont(TTFont("DejaVu", _DEJAVU_SANS))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", _DEJAVU_BOLD))
    if Path(_ARABIC_FONT).exists():
        pdfmetrics.registerFont(TTFont("NotoArabic", _ARABIC_FONT))
    _FONT_REGISTERED = True


def make_pdf(num_pages: int = 3) -> bytes:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_password_protected_pdf(password: str = "secret", num_pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password=password, owner_password=None)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_corrupt_pdf() -> bytes:
    return b"%PDF-1.4\n" + b"\x00garbage\x01\x02" * 500


def make_empty_pdf() -> bytes:
    return b""


def _tiny_png(width: int = 64, height: int = 64) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes([120, 150, 200]) * width
    idat = zlib.compress(row * height)
    return header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _add_bookmarks(buffer: BytesIO, outline: list[tuple[str, int | None]]) -> bytes:
    """Add outline items; entries are (title, parent_index|None).

    Page indices are located by searching the extracted text, so callers do
    not need to guess page numbers.
    """
    reader = PdfReader(buffer)
    normalized = re.compile(r"\s+")
    page_texts = [
        normalized.sub(" ", page.extract_text(extraction_mode="layout") or "").lower()
        for page in reader.pages
    ]
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    parents: dict[int, object] = {}
    for title, parent_index in outline:
        needle = normalized.sub(" ", title).lower()
        page_index = next((i for i, text in enumerate(page_texts) if needle in text), 0)
        parent = parents.get(parent_index) if parent_index is not None else None
        parents[len(parents)] = writer.add_outline_item(title, page_index, parent=parent)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def make_structured_pdf() -> bytes:
    """Book with chapters, nested sections, paragraphs (EN + Malay), table,
    figure, and footnote. Outline bookmarks are added via pypdf."""
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_DEJAVU_SANS).exists():
        styles["BodyText"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu-Bold"
        styles["Heading2"].fontName = "DejaVu-Bold"

    story = [
        Paragraph("Chapter 1: Foundations", styles["Heading1"]),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 1.1 The Problem", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Memory is the faculty by which information is encoded, stored, and "
            "retrieved in the human brain. This opening paragraph discusses the "
            "core problem this book addresses.",
            styles["BodyText"],
        ),
        Paragraph(
            "Ingatan ialah keupayaan otak untuk mengekod, menyimpan dan mengingat "
            "semula maklumat. Ini adalah contoh teks Bahasa Melayu dalam dokumen ini.",
            styles["BodyText"],
        ),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 1.2 Experimental Methods", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Participants completed a series of recall tasks. The results are "
            "summarised in the table below.",
            styles["BodyText"],
        ),
        Table(
            [["Group", "Recall (%)", "N"], ["A", "72", "40"], ["B", "85", "45"], ["C", "61", "38"]],
            colWidths=[4 * cm, 4 * cm, 4 * cm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            ),
        ),
        Spacer(1, 0.3 * cm),
        Paragraph("Figure 1. Experimental setup diagram.", styles["BodyText"]),
        Image(BytesIO(_tiny_png()), width=3 * cm, height=3 * cm),
        Spacer(1, 0.3 * cm),
        Paragraph("Chapter 2: Advanced Topics", styles["Heading1"]),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 2.1 Consolidation", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Consolidation stabilises memories over time. A footnote below "
            "clarifies the mechanism.",
            styles["BodyText"],
        ),
        Paragraph(
            "1 A leading hypothesis links consolidation to slow-wave sleep.", styles["BodyText"]
        ),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 2.2 Retrieval Cues", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Retrieval cues improve recall accuracy significantly in controlled settings.",
            styles["BodyText"],
        ),
        Paragraph(
            "Concluding paragraph of chapter two with additional context and detail.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    outline = [
        ("Chapter 1: Foundations", None),
        ("Section 1.1 The Problem", 0),
        ("Section 1.2 Experimental Methods", 0),
        ("Chapter 2: Advanced Topics", None),
        ("Section 2.1 Consolidation", 3),
        ("Section 2.2 Retrieval Cues", 3),
    ]
    return _add_bookmarks(buffer, outline)


def make_plain_text_pdf() -> bytes:
    """Simple single-chapter text document without bookmarks."""
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build(
        [
            Paragraph("A Short Report", styles["Heading1"]),
            Paragraph(
                "This document contains plain text across two pages to verify "
                "per-page extraction and page numbering.",
                styles["BodyText"],
            ),
            Paragraph("Second page paragraph that should land on page two.", styles["BodyText"]),
            Paragraph(
                "A final paragraph ending the plain text fixture.",
                styles["BodyText"],
            ),
        ]
    )
    return buffer.getvalue()


def make_malay_pdf() -> bytes:
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_DEJAVU_SANS).exists():
        styles["BodyText"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu-Bold"
    doc.build(
        [
            Paragraph("Bab 1: Pengenalan", styles["Heading1"]),
            Paragraph(
                "Dokumen ini mengandungi teks berbahasa Melayu untuk menguji "
                "pengekstrakan teks bukan Inggeris.",
                styles["BodyText"],
            ),
            Paragraph(
                "Ayat kedua dalam perenggan pertama menyediakan konteks tambahan.",
                styles["BodyText"],
            ),
        ]
    )
    return buffer.getvalue()


def make_arabic_pdf() -> bytes:
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_ARABIC_FONT).exists():
        styles["BodyText"].fontName = "NotoArabic"
    doc.build(
        [
            Paragraph("نص باللغة العربية لاختبار استخراج النصوص", styles["BodyText"]),
            Paragraph(
                "هذا النص مكتوب باللغة العربية للتحقق من دعم اللغات في عملية الاستخراج.",
                styles["BodyText"],
            ),
        ]
    )
    return buffer.getvalue()


def make_two_column_pdf() -> bytes:
    _register_fonts()
    buffer = BytesIO()
    frame_left = Frame(2 * cm, 2 * cm, 8 * cm, 25 * cm, id="left")
    frame_right = Frame(11 * cm, 2 * cm, 8 * cm, 25 * cm, id="right")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.addPageTemplates([PageTemplate(id="columns", frames=[frame_left, frame_right])])
    styles = getSampleStyleSheet()
    story = []
    for index in range(8):
        story.append(
            Paragraph(
                f"Column paragraph {index}: This text is part of a two-column "
                "layout used to verify layout-aware extraction.",
                styles["BodyText"],
            )
        )
    doc.build(story)
    return buffer.getvalue()


def _render_to_png(pdf_bytes: bytes, page_number: int = 0, scale: float = 2.5) -> bytes:
    """Rasterise a page of a PDF to PNG bytes (needs the ``ocr`` extra)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(BytesIO(pdf_bytes))
    try:
        page = pdf[page_number]
        bitmap = page.render(scale=scale)
        output = BytesIO()
        bitmap.to_pil().convert("RGB").save(output, format="PNG")
        return output.getvalue()
    finally:
        pdf.close()


def _embed_image_page(pdf_bytes: bytes, source_page_index: int) -> bytes:
    """Build a single image-only PDF page (no text layer) from a rasterised
    source page, mimicking a scan."""
    png = _render_to_png(pdf_bytes, source_page_index)
    buffer = BytesIO()
    image_doc = SimpleDocTemplate(buffer, pagesize=A4)
    image_doc.build([Image(BytesIO(png), width=17 * cm, height=24 * cm)])
    return buffer.getvalue()


def make_scanned_pdf(num_pages: int = 2) -> bytes:
    """Image-only PDF: reportlab text rasterised to PNG and embedded with no
    text layer, mimicking a clean scan."""
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_DEJAVU_SANS).exists():
        styles["BodyText"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu-Bold"
    story = [
        Paragraph("Scanned Document Title", styles["Heading1"]),
        Paragraph(
            "This is a scanned page. Optical character recognition must recover "
            "this text from the image alone.",
            styles["BodyText"],
        ),
        PageBreak(),
    ]
    for index in range(2, num_pages + 1):
        story.append(Paragraph(f"Additional paragraph on page {index}.", styles["BodyText"]))
        story.append(
            Paragraph(
                "A second sentence provides more material for the OCR engine to "
                "recognise so the page is not sparse.",
                styles["BodyText"],
            )
        )
        if index < num_pages:
            story.append(PageBreak())
    doc.build(story)

    output = PdfWriter()
    for page_index in range(len(PdfReader(buffer).pages)):
        embedded = _embed_image_page(buffer.getvalue(), page_index)
        output.append(PdfReader(BytesIO(embedded)))
    out = BytesIO()
    output.write(out)
    return out.getvalue()


def make_mixed_pdf() -> bytes:
    """Mixed document: page 1 has text + image, page 2 is a scanned image."""
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_DEJAVU_SANS).exists():
        styles["BodyText"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu-Bold"
    doc.build(
        [
            Paragraph("Mixed Document", styles["Heading1"]),
            Paragraph(
                "Page one contains real text together with a small figure.",
                styles["BodyText"],
            ),
            Image(BytesIO(_tiny_png()), width=3 * cm, height=3 * cm),
            PageBreak(),
            Paragraph("Page two of this document.", styles["BodyText"]),
        ]
    )
    scanned_page = _embed_image_page(buffer.getvalue(), 1)
    output = PdfWriter()
    output.add_page(PdfReader(buffer).pages[0])
    output.append(PdfReader(BytesIO(scanned_page)))
    out = BytesIO()
    output.write(out)
    return out.getvalue()


def make_image_only_pdf(num_pages: int = 1) -> bytes:
    """PDF of image-only pages (no text layer) using a generated PNG.

    Does not require the ``ocr`` extra (unlike :func:`make_scanned_pdf`).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.build(
        [Image(BytesIO(_tiny_png()), width=17 * cm, height=24 * cm) for _ in range(num_pages)]
    )
    return buffer.getvalue()


def make_search_book_pdf() -> bytes:
    """Multi-page book with chapters, sections, and a results table, used by
    the retrieval evaluation suite and search integration tests."""
    _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    if Path(_DEJAVU_SANS).exists():
        styles["BodyText"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu-Bold"
        styles["Heading2"].fontName = "DejaVu-Bold"

    story = [
        Paragraph("Chapter 1: Foundations", styles["Heading1"]),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 1.1 The Problem", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Memory is the faculty by which information is encoded, stored, and "
            "retrieved in the human brain. Understanding this process is the "
            "central problem of the book.",
            styles["BodyText"],
        ),
        Paragraph(
            "Memory formation involves multiple stages that begin at the moment of perception.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("Section 1.2 Experimental Methods", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Participants completed a series of recall tasks over two sessions. "
            "The results are summarised in the table below.",
            styles["BodyText"],
        ),
        Table(
            [
                ["Group", "Recall (%)", "N"],
                ["A", "72", "40"],
                ["B", "85", "45"],
                ["C", "61", "38"],
            ],
            colWidths=[4 * cm, 4 * cm, 4 * cm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            ),
        ),
        Paragraph(
            "Group B achieved the highest recall percentage across all sessions.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("Chapter 2: Advanced Topics", styles["Heading1"]),
        Spacer(1, 0.3 * cm),
        Paragraph("Section 2.1 Consolidation", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Consolidation stabilises memories over time. A leading hypothesis "
            "links consolidation to slow-wave sleep during the night.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("Section 2.2 Retrieval Cues", styles["Heading2"]),
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Retrieval cues improve recall accuracy significantly in controlled "
            "settings, especially when the cue matches the original encoding "
            "context.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    outline = [
        ("Chapter 1: Foundations", None),
        ("Section 1.1 The Problem", 0),
        ("Section 1.2 Experimental Methods", 0),
        ("Chapter 2: Advanced Topics", None),
        ("Section 2.1 Consolidation", 3),
        ("Section 2.2 Retrieval Cues", 3),
    ]
    return _add_bookmarks(buffer, outline)
