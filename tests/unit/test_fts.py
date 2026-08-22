from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory
from mindweaver.models import ChunkRecord
from mindweaver.search.fts import build_match_query, index_document, keyword_search


def _settings(tmp_path) -> Settings:
    return Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/f.db"))


def _record(chunk_id: str, text: str, document_id: str = "doc_1", chapter: str | None = None):
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=document_id,
        position=0,
        page_start=1,
        page_end=1,
        chapter=chapter,
        section=None,
        subsection=None,
        section_path="[]",
        text=text,
        token_count=len(text.split()),
        parent_chunk_id=None,
    )


def test_build_match_query_quotes_words():
    assert build_match_query("memory consolidation") == '"memory" AND "consolidation"'
    assert build_match_query("OR sneaky AND") == '"OR" AND "sneaky" AND "AND"'


def test_keyword_search_finds_matching_chunk(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        index_document(
            session,
            [
                _record("chunk_1", "Memory is the faculty by which information is encoded."),
                _record("chunk_2", "Consolidation stabilises memories during sleep."),
            ],
        )
        session.commit()
        hits = keyword_search(session, "consolidation memories")
        ids = [h["chunk_id"] for h in hits]
        assert "chunk_2" in ids


def test_keyword_search_indexes_section_names(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        index_document(
            session,
            [_record("chunk_1", "Some body text.", chapter="Chapter 2: Advanced Topics")],
        )
        session.commit()
        hits = keyword_search(session, "advanced topics")
        assert any(h["chunk_id"] == "chunk_1" for h in hits)


def test_keyword_search_document_filter(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        index_document(
            session,
            [
                _record("a", "memory consolidation", document_id="doc_a"),
                _record("b", "memory consolidation", document_id="doc_b"),
            ],
        )
        session.commit()
        hits = keyword_search(session, "consolidation", document_id="doc_a")
        assert [h["chunk_id"] for h in hits] == ["a"]


def test_keyword_search_empty_query(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        assert keyword_search(session, "  ") == []


def test_keyword_search_natural_language_falls_back_to_or(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        index_document(
            session,
            [
                _record("chunk_1", "A design system has to scale across many products."),
            ],
        )
        session.commit()
        question = "What is a design system according to this book exactly?"
        hits = keyword_search(session, question, limit=5)
        ids = [h["chunk_id"] for h in hits]
        assert "chunk_1" in ids


def test_keyword_search_prefers_and_matches_over_or(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        index_document(
            session,
            [
                _record("both", "memory consolidation improves recall"),
                _record("only_memory", "memory palace techniques"),
            ],
        )
        session.commit()
        hits = keyword_search(session, "memory consolidation", limit=5)
        assert hits[0]["chunk_id"] == "both"
