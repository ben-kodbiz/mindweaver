from pathlib import Path

import pytest
from fixtures.pdf import (
    make_arabic_pdf,
    make_malay_pdf,
    make_plain_text_pdf,
    make_structured_pdf,
    make_two_column_pdf,
)
from mindweaver.document_model import BlockType
from mindweaver.extraction.base import ExtractionError
from mindweaver.extraction.pypdf_processor import PyPdfProcessor


@pytest.fixture(scope="module")
def _tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("pdfs")


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_plain_text_pages_and_blocks(tmp_path):
    path = _write(tmp_path, "plain.pdf", make_plain_text_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="plain.pdf")
    doc = result.document
    assert len(doc.pages) >= 1
    assert doc.blocks
    assert all(block.page_number >= 1 for block in doc.blocks)
    assert all(block.document_id == "d1" for block in doc.blocks)


def test_chapters_and_nested_sections(tmp_path):
    path = _write(tmp_path, "structured.pdf", make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="structured.pdf")
    doc = result.document

    chapter_titles = {s.title for s in doc.sections}
    assert "Chapter 1: Foundations" in chapter_titles
    assert "Chapter 2: Advanced Topics" in chapter_titles

    chapter1 = next(s for s in doc.sections if s.title == "Chapter 1: Foundations")
    section_titles = {child.title for child in chapter1.children}
    assert "Section 1.1 The Problem" in section_titles
    assert "Section 1.2 Experimental Methods" in section_titles


def test_paragraph_knows_page_chapter_and_section(tmp_path):
    path = _write(tmp_path, "structured.pdf", make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="structured.pdf")
    doc = result.document

    paragraph = next(
        b
        for b in doc.blocks
        if b.block_type == BlockType.PARAGRAPH and b.text.startswith("Memory is the faculty")
    )
    assert paragraph.page_number >= 1
    assert paragraph.section_path == [
        "Chapter 1: Foundations",
        "Section 1.1 The Problem",
    ]
    assert paragraph.section_path[0] == "Chapter 1: Foundations"  # chapter
    assert paragraph.section_path[-1] == "Section 1.1 The Problem"  # parent section


def test_heading_blocks_are_detected(tmp_path):
    path = _write(tmp_path, "structured.pdf", make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="structured.pdf")
    doc = result.document
    headings = [b for b in doc.blocks if b.block_type == BlockType.HEADING]
    assert any(h.text == "Chapter 1: Foundations" for h in headings)
    assert any(h.text == "Section 2.2 Retrieval Cues" for h in headings)


def test_table_text_is_preserved(tmp_path):
    path = _write(tmp_path, "structured.pdf", make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="structured.pdf")
    all_text = "\n".join(b.text for b in result.document.blocks)
    assert "Group" in all_text
    assert "Recall" in all_text


def test_malay_text_extraction(tmp_path):
    path = _write(tmp_path, "malay.pdf", make_malay_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="malay.pdf")
    all_text = "\n".join(b.text for b in result.document.blocks)
    assert "Bab 1: Pengenalan" in all_text
    assert "berbahasa Melayu" in all_text


def test_two_column_text_extraction(tmp_path):
    path = _write(tmp_path, "two_column.pdf", make_two_column_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="two_column.pdf")
    all_text = "\n".join(b.text for b in result.document.blocks)
    assert "Column paragraph 0" in all_text
    assert "Column paragraph 7" in all_text


def test_arabic_text_extraction(tmp_path):
    path = _write(tmp_path, "arabic.pdf", make_arabic_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="arabic.pdf")
    all_text = "\n".join(b.text for b in result.document.blocks)
    assert any(ord(ch) > 0x0600 for ch in all_text)


def test_corrupt_pdf_raises_extraction_error(tmp_path):
    path = _write(tmp_path, "corrupt.pdf", b"%PDF-1.4\n\x00\x01garbage")
    with pytest.raises(ExtractionError):
        PyPdfProcessor().extract(path, document_id="d1", filename="corrupt.pdf")


def test_no_double_heading_blocks_for_single_heading(tmp_path):
    path = _write(tmp_path, "structured.pdf", make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="structured.pdf")
    headings = [
        b
        for b in result.document.blocks
        if b.block_type == BlockType.HEADING and b.text == "Chapter 1: Foundations"
    ]
    assert len(headings) == 1
