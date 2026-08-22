from mindweaver.document_model import (
    BlockType,
    BoundingBox,
    CanonicalDocument,
    ContentBlock,
    Page,
    Section,
)


def test_canonical_round_trip():
    doc = CanonicalDocument(
        document_id="doc_1",
        source_filename="book.pdf",
        processor="pypdf",
        pages=[Page(page_number=1, width=600.0, height=800.0)],
        sections=[
            Section(
                id="sec_0",
                title="Chapter 1",
                level=1,
                page_number=1,
                section_path=["Chapter 1"],
                children=[
                    Section(
                        id="sec_1",
                        title="Section 1.1",
                        level=2,
                        page_number=1,
                        section_path=["Chapter 1", "Section 1.1"],
                    )
                ],
            )
        ],
        blocks=[
            ContentBlock(
                block_id="blk_0",
                document_id="doc_1",
                page_number=1,
                block_type=BlockType.PARAGRAPH,
                text="hello",
                section_path=["Chapter 1", "Section 1.1"],
                bbox=BoundingBox(page_number=1, left=0.0, top=0.0, right=100.0, bottom=20.0),
                source_confidence=0.98,
            )
        ],
    )

    payload = doc.model_dump_json()
    restored = CanonicalDocument.model_validate_json(payload)
    assert restored == doc
    assert restored.blocks[0].section_path == ["Chapter 1", "Section 1.1"]
    assert restored.blocks[0].bbox.right == 100.0


def test_block_type_values_are_lowercase():
    assert BlockType.PARAGRAPH == "paragraph"
    assert BlockType.HEADING == "heading"
    assert BlockType.TABLE == "table"
