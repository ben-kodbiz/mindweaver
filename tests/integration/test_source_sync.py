from fixtures.pdf import make_search_book_pdf
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.documents import chunk_source_regions
from mindweaver.graph.selection import extract_selection
from mindweaver.graph.service import get_graph
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.indexing import index_document_chunks


def _settings(tmp_path) -> Settings:
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/s.db"))
    settings.llm.provider = "stub"
    return settings


def _setup(session, settings) -> Document:
    session.add(
        Document(
            id="doc_1", title="Search Book", original_filename="b.pdf", sha256="a" * 64, file_size=1
        )
    )
    session.flush()
    chunks = [
        ChunkRecord(
            chunk_id="c1",
            document_id="doc_1",
            position=0,
            page_start=1,
            page_end=1,
            chapter="Chapter 1",
            section="Section 1.1",
            subsection=None,
            section_path='["Chapter 1: Foundations", "Section 1.1 The Problem"]',
            text="Memory is the faculty by which information is encoded, stored, and retrieved.",
            token_count=12,
            parent_chunk_id=None,
        )
    ]
    session.add_all(chunks)
    session.flush()
    index_document_chunks(session, settings, session.get(Document, "doc_1"), chunks)
    return session.get(Document, "doc_1")


def test_selection_preview_does_not_write(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, settings)

        result = extract_selection(
            session, settings, document, "Working memory holds active information.", 2
        )
        assert result["added"] is False
        assert any(node["label"] == "Working memory" for node in result["candidates"]["nodes"])
        graph = get_graph(session, document.id)
        assert graph is None  # nothing written yet


def test_selection_confirm_adds_to_graph(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, settings)

        result = extract_selection(
            session, settings, document, "Working memory holds active information.", 2, confirm=True
        )
        assert result["added"] is True
        graph = get_graph(session, document.id)
        assert graph is not None
        assert any(node.label == "Working memory" for node in graph.nodes)
        assert any(edge.relation.value == "part_of" for edge in graph.edges)


def test_source_regions_with_bbox(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, settings)

        from mindweaver import storage as storage_module
        from mindweaver.document_model import (
            BlockType,
            BoundingBox,
            CanonicalDocument,
            ContentBlock,
            Page,
        )

        canonical = CanonicalDocument(
            document_id="doc_1",
            source_filename="b.pdf",
            processor="docling",
            pages=[Page(page_number=1, width=600.0, height=800.0)],
            blocks=[
                ContentBlock(
                    block_id="b1",
                    document_id="doc_1",
                    page_number=1,
                    block_type=BlockType.PARAGRAPH,
                    text="Memory is the faculty.",
                    section_path=["Chapter 1: Foundations", "Section 1.1 The Problem"],
                    bbox=BoundingBox(
                        page_number=1, left=50.0, top=100.0, right=400.0, bottom=120.0
                    ),
                ),
                ContentBlock(
                    block_id="b2",
                    document_id="doc_1",
                    page_number=1,
                    block_type=BlockType.PARAGRAPH,
                    text="Stored and retrieved in the brain.",
                    section_path=["Chapter 1: Foundations", "Section 1.1 The Problem"],
                ),
            ],
        )
        storage_module.save_derived_json(
            settings, "doc_1", "canonical.json", canonical.model_dump_json()
        )

        result = chunk_source_regions(session, settings, document, "c1")
        assert result is not None
        assert len(result["regions"]) == 2
        with_bbox = next((r for r in result["regions"] if "bbox" in r), None)
        assert with_bbox is not None
        assert with_bbox["bbox"]["left"] == 50.0
        without_bbox = next((r for r in result["regions"] if "bbox" not in r), None)
        assert without_bbox is not None
        assert without_bbox["text"] == "Stored and retrieved in the brain."


def test_source_regions_unknown_chunk(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, settings)
        assert chunk_source_regions(session, settings, document, "nope") is None


def test_selection_api_flow(client, app_settings):
    app_settings.llm.provider = "stub"
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    doc = resp.json()

    preview = client.post(
        f"/api/v1/documents/{doc['id']}/mindmap/selection",
        json={"text": "Working memory holds active information.", "page_number": 1},
    )
    assert preview.status_code == 200
    assert preview.json()["added"] is False

    confirm = client.post(
        f"/api/v1/documents/{doc['id']}/mindmap/selection",
        json={
            "text": "Working memory holds active information.",
            "page_number": 1,
            "confirm": True,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["added"] is True

    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert any(node["label"] == "Working memory" for node in graph["nodes"])


def test_source_api_returns_regions(client, app_settings):
    app_settings.llm.provider = "stub"
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    doc = resp.json()
    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert chunks
    chunk_id = chunks[0]["chunk_id"]

    source = client.get(f"/api/v1/documents/{doc['id']}/chunks/{chunk_id}/source")
    assert source.status_code == 200
    body = source.json()
    assert body["chunk_id"] == chunk_id
    assert body["regions"]
    assert all(region["page_number"] >= 1 for region in body["regions"])
