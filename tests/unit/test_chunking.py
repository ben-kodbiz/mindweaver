from mindweaver.chunking.structural import chunk_document
from mindweaver.document_model import (
    BlockType,
    CanonicalDocument,
    ContentBlock,
    Page,
)


def _doc(blocks: list[ContentBlock]) -> CanonicalDocument:
    page_count = max((b.page_number for b in blocks), default=0)
    return CanonicalDocument(
        document_id="doc_1",
        source_filename="book.pdf",
        processor="pypdf",
        pages=[Page(page_number=i + 1) for i in range(page_count)],
        blocks=blocks,
    )


def _block(page: int, text: str, path: list[str], block_type=BlockType.PARAGRAPH, i: int = 0):
    return ContentBlock(
        block_id=f"blk_{i}",
        document_id="doc_1",
        page_number=page,
        block_type=block_type,
        text=text,
        section_path=path,
    )


def test_small_section_single_chunk():
    doc = _doc(
        [
            _block(1, "Chapter 1: Foundations", ["Chapter 1: Foundations"], BlockType.HEADING, 0),
            _block(1, "First paragraph.", ["Chapter 1: Foundations"], i=1),
            _block(1, "Second paragraph.", ["Chapter 1: Foundations"], i=2),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.page_start == 1 and chunk.page_end == 1
    assert chunk.chapter == "Chapter 1: Foundations"
    assert chunk.text.startswith("Chapter 1: Foundations")
    assert "First paragraph." in chunk.text
    assert chunk.token_count > 0


def test_nested_sections_preserve_hierarchy():
    doc = _doc(
        [
            _block(1, "Ch1", ["Ch1"], BlockType.HEADING, 0),
            _block(1, "S1.1", ["Ch1", "S1.1"], BlockType.HEADING, 1),
            _block(1, "content a", ["Ch1", "S1.1"], i=2),
            _block(2, "S1.2", ["Ch1", "S1.2"], BlockType.HEADING, 3),
            _block(2, "content b", ["Ch1", "S1.2"], i=4),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    assert len(chunks) == 2
    sec11 = next(c for c in chunks if c.section == "S1.1")
    sec12 = next(c for c in chunks if c.section == "S1.2")
    assert sec11.section_path == ["Ch1", "S1.1"]
    assert sec11.chapter == "Ch1"
    assert sec11.section == "S1.1"
    assert sec11.subsection is None
    # "Ch1" has no body content -> no chapter chunk, so no parent link.
    assert sec11.parent_chunk_id is None
    assert sec12.parent_chunk_id is None


def test_parent_chunk_link_for_nested_section():
    doc = _doc(
        [
            _block(1, "Ch1", ["Ch1"], BlockType.HEADING, 0),
            _block(1, "chapter intro", ["Ch1"], i=1),
            _block(2, "S1.1", ["Ch1", "S1.1"], BlockType.HEADING, 2),
            _block(2, "section content", ["Ch1", "S1.1"], i=3),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    by_section = {c.section or c.chapter: c for c in chunks}
    chapter = by_section["Ch1"]
    section = by_section["S1.1"]
    assert section.parent_chunk_id == chapter.chunk_id


def test_huge_section_is_split_without_mid_paragraph():
    paragraphs = [_block(1, f"Paragraph {i} " + "word " * 100, ["Big"], i=i) for i in range(20)]
    doc = _doc(paragraphs)
    chunks = chunk_document(doc, max_chars=400)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 400 + 500  # allow one oversized atomic paragraph
        assert "Paragraph 20 " not in chunk.text  # sanity
    # no paragraph should be torn in half: every chunk starts a paragraph boundary
    for chunk in chunks:
        body = chunk.text.split("\n\n", 1)[-1]
        assert body.startswith("Paragraph ")


def test_oversized_single_paragraph_split_on_sentences():
    doc = _doc([_block(1, "Sentence one. " * 60, ["Huge"], i=0)])
    chunks = chunk_document(doc, max_chars=200)
    assert len(chunks) >= 2
    all_text = " ".join(c.text for c in chunks)
    assert all_text.count("Sentence one.") == 60
    # sentences not split mid-word
    for chunk in chunks:
        assert chunk.text.strip().endswith(".")


def test_table_never_split():
    table_text = "\t".join(["Group", "Recall", "N", "A", "72", "40"])
    doc = _doc(
        [_block(1, "Table title", ["T"], i=0), _block(1, table_text, ["T"], BlockType.TABLE, i=1)]
    )
    chunks = chunk_document(doc, max_chars=1000)
    assert len(chunks) == 1
    assert "Group" in chunks[0].text


def test_multi_page_section_page_range():
    doc = _doc(
        [
            _block(1, "S1", ["S1"], BlockType.HEADING, 0),
            _block(1, "content page 1", ["S1"], i=1),
            _block(2, "content page 2", ["S1"], i=2),
            _block(3, "content page 3", ["S1"], i=3),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 3


def test_caption_attached_to_content():
    doc = _doc(
        [
            _block(1, "S1", ["S1"], BlockType.HEADING, 0),
            _block(1, "Figure 1. A diagram.", ["S1"], BlockType.CAPTION, 1),
            _block(1, "The figure shows the results.", ["S1"], i=2),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    assert len(chunks) == 1
    assert "Figure 1. A diagram." in chunks[0].text
    assert "The figure shows" in chunks[0].text


def test_ocr_generated_blocks_chunked(tmp_path):
    ocr_blocks = [
        _block(1, "Scanned Document Title", [], BlockType.HEADING, 0),
        _block(1, "OCR recognised line one.", [], i=1),
        _block(2, "OCR recognised line two.", [], i=2),
    ]
    chunks = chunk_document(_doc(ocr_blocks), max_chars=2000)
    assert len(chunks) == 1
    assert "OCR recognised line one." in chunks[0].text
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2


def test_empty_document_no_chunks():
    doc = _doc([])
    assert chunk_document(doc) == []


def test_acceptance_reconstruct_book_path():
    doc = _doc(
        [
            _block(1, "Chapter 1: Foundations", ["Chapter 1: Foundations"], BlockType.HEADING, 0),
            _block(
                1,
                "Section 1.1 The Problem",
                ["Chapter 1: Foundations", "Section 1.1 The Problem"],
                BlockType.HEADING,
                1,
            ),
            _block(
                2,
                "Memory is the faculty by which information is encoded.",
                ["Chapter 1: Foundations", "Section 1.1 The Problem"],
                i=2,
            ),
        ]
    )
    chunks = chunk_document(doc, max_chars=2000)
    chunk = next(c for c in chunks if c.section == "Section 1.1 The Problem")
    assert chunk.section_path == ["Chapter 1: Foundations", "Section 1.1 The Problem"]
    assert chunk.chapter == "Chapter 1: Foundations"
    assert chunk.section == "Section 1.1 The Problem"
    assert chunk.page_start == 1 and chunk.page_end == 2
    assert "Memory is the faculty" in chunk.text
    assert chunk.text.startswith("Chapter 1: Foundations")
