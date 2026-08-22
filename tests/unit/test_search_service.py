from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.models import ChunkRecord
from mindweaver.search.service import search


def _settings(tmp_path) -> Settings:
    return Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/s.db"))


def _chunk(chunk_id: str, text: str, chapter: str, section: str, page: int):
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id="doc_1",
        position=0,
        page_start=page,
        page_end=page,
        chapter=chapter,
        section=section,
        subsection=None,
        section_path=f'["{chapter}", "{section}"]',
        text=text,
        token_count=len(text.split()),
        parent_chunk_id=None,
    )


def test_hybrid_search_merges_and_dedupes(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        from mindweaver.models import Document
        from mindweaver.search.indexing import index_document_chunks

        session.add(
            Document(id="doc_1", title="x", original_filename="x.pdf", sha256="a" * 64, file_size=1)
        )
        session.flush()
        records = [
            _chunk(
                "a",
                "Memory is the faculty by which information is encoded.",
                "Chapter 1",
                "Section 1.1",
                1,
            ),
            _chunk(
                "b",
                "Consolidation stabilises memories during sleep.",
                "Chapter 2",
                "Section 2.1",
                3,
            ),
        ]
        session.add_all(records)
        session.flush()
        index_document_chunks(session, _settings(tmp_path), session.get(Document, "doc_1"), records)

        response = search(session, _settings(tmp_path), "consolidation memories sleep", limit=10)

    assert response.total == 1
    hit = response.results[0]
    assert hit.chunk_id == "b"
    assert hit.chapter == "Chapter 2"
    assert hit.section == "Section 2.1"
    assert hit.page_start == 3
    assert hit.rank == 1
    assert hit.keyword_score is not None
    assert hit.vector_score is not None
    assert hit.rerank_score is not None
    assert hit.retrieval_score > 0


def test_negative_query_returns_nothing(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        from mindweaver.models import Document
        from mindweaver.search.indexing import index_document_chunks

        session.add(
            Document(id="doc_1", title="x", original_filename="x.pdf", sha256="a" * 64, file_size=1)
        )
        session.flush()
        record = _chunk(
            "a",
            "Memory is the faculty by which information is encoded.",
            "Chapter 1",
            "Section 1.1",
            1,
        )
        session.add(record)
        session.flush()
        index_document_chunks(
            session, _settings(tmp_path), session.get(Document, "doc_1"), [record]
        )

        response = search(
            session, _settings(tmp_path), "whales photosynthesise underwater", limit=10
        )

    assert response.total == 0
    assert response.results == []


def test_document_scoped_search(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        from mindweaver.models import Document
        from mindweaver.search.indexing import index_document_chunks

        session.add(
            Document(id="doc_1", title="x", original_filename="x.pdf", sha256="a" * 64, file_size=1)
        )
        session.add(
            Document(id="doc_2", title="y", original_filename="y.pdf", sha256="b" * 64, file_size=1)
        )
        session.flush()

        record_a = _chunk("a1", "memory consolidation across the cortex", "Ch1", "S1", 1)
        record_a.document_id = "doc_1"
        record_b = _chunk("b1", "memory consolidation across the cortex", "Ch1", "S1", 1)
        record_b.document_id = "doc_2"
        session.add_all([record_a, record_b])
        session.flush()

        index_document_chunks(
            session, _settings(tmp_path), session.get(Document, "doc_1"), [record_a]
        )
        index_document_chunks(
            session, _settings(tmp_path), session.get(Document, "doc_2"), [record_b]
        )

        response = search(
            session,
            _settings(tmp_path),
            "memory consolidation cortex",
            document_id="doc_1",
            limit=10,
        )

    assert response.total == 1
    assert response.results[0].document_id == "doc_1"


def test_keyword_scores_are_distinct_and_best_is_one(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        from mindweaver.models import Document
        from mindweaver.search.indexing import index_document_chunks

        session.add(
            Document(id="doc_1", title="x", original_filename="x.pdf", sha256="a" * 64, file_size=1)
        )
        session.flush()
        records = [
            _chunk("best", "design system scaling tokens tokens tokens", "Ch1", "S1", 1),
            _chunk("weak", "the design is nice and the system runs", "Ch1", "S2", 2),
            _chunk("other", "unrelated content about whales and oceans", "Ch2", "S3", 3),
        ]
        session.add_all(records)
        session.flush()
        index_document_chunks(
            session, _settings(tmp_path), session.get(Document, "doc_1"), records
        )

        response = search(
            session,
            _settings(tmp_path),
            "What is a design system for scaling tokens?",
            limit=10,
        )

    by_id = {hit.chunk_id: hit for hit in response.results}
    assert by_id["best"].keyword_score == 1.0
    assert 0.0 < by_id["weak"].keyword_score < 1.0
