import pytest
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.graph.expand import NodeNotFoundError
from mindweaver.graph.service import get_graph
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.indexing import index_document_chunks


def _settings(tmp_path) -> Settings:
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/x.db"))
    settings.llm.provider = "stub"
    return settings


def _chunk(chunk_id: str, text: str, page: int):
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id="doc_1",
        position=0,
        page_start=page,
        page_end=page,
        chapter="Chapter 2",
        section="Section 2.1",
        subsection=None,
        section_path='["Chapter 2: Advanced Topics", "Section 2.1 Consolidation"]',
        text=text,
        token_count=len(text.split()),
        parent_chunk_id=None,
    )


def _setup(session, tmp_path):
    settings = _settings(tmp_path)
    session.add(
        Document(
            id="doc_1", title="Search Book", original_filename="b.pdf", sha256="a" * 64, file_size=1
        )
    )
    session.flush()
    chunks = [
        _chunk(
            "c1",
            (
                "Memory is the faculty by which information is encoded, "
                "stored, and retrieved in the human brain."
            ),
            1,
        ),
        _chunk(
            "c2",
            (
                "Consolidation stabilises memories over time and links to "
                "slow-wave sleep during the night."
            ),
            3,
        ),
        _chunk("c3", "Retrieval cues improve recall accuracy in controlled settings.", 4),
    ]
    session.add_all(chunks)
    session.flush()
    index_document_chunks(session, settings, session.get(Document, "doc_1"), chunks)

    from mindweaver.graph.service import run_graph_extraction

    run_graph_extraction(session, settings, session.get(Document, "doc_1"))
    session.flush()
    return session.get(Document, "doc_1")


def test_expand_valid_node_merges_new_concepts(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)

        from mindweaver.graph.expand import expand_node

        added_nodes, added_edges, warnings, version = expand_node(
            session, settings, document, "concept:consolidation"
        )

        labels = {node.label for node in added_nodes}
        assert "Slow-wave sleep" in labels
        assert "Memory" not in labels  # already exists -> deduped
        assert added_edges
        assert version == 2

        graph = get_graph(session, document.id)
        assert graph is not None
        assert any(node.label == "Slow-wave sleep" for node in graph.nodes)


def test_expand_repeatedly_is_idempotent(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)

        from mindweaver.graph.expand import expand_node

        first_nodes, _, _, _ = expand_node(session, settings, document, "concept:consolidation")
        assert first_nodes
        graph_after_first = get_graph(session, document.id)
        assert graph_after_first is not None

        second_nodes, second_edges, _, _ = expand_node(
            session, settings, document, "concept:consolidation"
        )
        assert second_nodes == []
        assert second_edges == []
        graph_after_second = get_graph(session, document.id)
        assert graph_after_second is not None
        assert len(graph_after_second.nodes) == len(graph_after_first.nodes)


def test_expand_leaf_node_still_works(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)

        from mindweaver.graph.expand import expand_node

        added_nodes, _, _, _ = expand_node(session, settings, document, "person:researchers")
        assert added_nodes  # stub still returns concepts; new ones are merged


def test_expand_unknown_node_raises(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)

        from mindweaver.graph.expand import expand_node

        with pytest.raises(NodeNotFoundError):
            expand_node(session, settings, document, "concept:nope")


def test_expand_invalid_json_leaves_graph_unchanged(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)
        before = get_graph(session, document.id)
        assert before is not None

        from mindweaver.graph import expand as expand_module
        from mindweaver.graph.extractor import GraphExtractionError
        from mindweaver.llm.stub import StubLLMProvider

        class BrokenStub(StubLLMProvider):
            def complete(self, messages, **kwargs):
                return "no json here"

        original = expand_module.get_llm_provider
        expand_module.get_llm_provider = lambda settings: BrokenStub()  # type: ignore[assignment]
        try:
            with pytest.raises(GraphExtractionError):
                expand_module.expand_node(session, settings, document, "concept:consolidation")
        finally:
            expand_module.get_llm_provider = original

        after = get_graph(session, document.id)
        assert after is not None
        assert len(after.nodes) == len(before.nodes)
        assert after.version == before.version


def test_expand_timeout_is_atomic(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        document = _setup(session, tmp_path)
        before = get_graph(session, document.id)
        assert before is not None

        from mindweaver.graph import expand as expand_module
        from mindweaver.llm.stub import StubLLMProvider

        class TimeoutStub(StubLLMProvider):
            def complete(self, messages, **kwargs):
                raise TimeoutError("llm timed out")

        original = expand_module.get_llm_provider
        expand_module.get_llm_provider = lambda settings: TimeoutStub()  # type: ignore[assignment]
        try:
            with pytest.raises(TimeoutError):
                expand_module.expand_node(session, settings, document, "concept:consolidation")
        finally:
            expand_module.get_llm_provider = original

        after = get_graph(session, document.id)
        assert after is not None
        assert len(after.nodes) == len(before.nodes)
