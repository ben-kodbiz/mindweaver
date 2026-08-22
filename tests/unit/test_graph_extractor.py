import pytest
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.graph.extractor import GraphExtractionError, extract_graph, normalize_graph
from mindweaver.graph.types import GraphEdgeType, GraphNodeType
from mindweaver.llm.stub import StubLLMProvider
from mindweaver.models import ChunkRecord, Document


def _chunk(chunk_id: str, text: str, page: int = 1):
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id="doc_1",
        position=0,
        page_start=page,
        page_end=page,
        chapter="Chapter 1",
        section=None,
        subsection=None,
        section_path='["Chapter 1"]',
        text=text,
        token_count=len(text.split()),
        parent_chunk_id=None,
    )


def test_normalize_dedupes_duplicate_concepts():
    chunks = [_chunk("c1", "Memory is the faculty for encoding information.")]
    payload = {
        "concepts": [
            {"label": "Memory", "type": "concept", "definition": "def one"},
            {"label": "Memory", "type": "concept", "definition": "def two"},
        ],
        "relations": [],
    }
    nodes, edges, warnings = normalize_graph(payload, "doc_1", chunks)
    memory_nodes = [n for n in nodes if n.label == "Memory"]
    assert len(memory_nodes) == 1
    assert any("duplicate" in w for w in warnings)


def test_normalize_invalid_node_type_defaults_to_concept():
    payload = {
        "concepts": [{"label": "X", "type": "bogus", "definition": ""}],
        "relations": [],
    }
    nodes, _, warnings = normalize_graph(payload, "doc_1", [_chunk("c1", "X appears here")])
    assert nodes[0].type == GraphNodeType.CONCEPT
    assert any("unknown node type" in w for w in warnings)


def test_normalize_invalid_relation_skipped():
    payload = {
        "concepts": [{"label": "A", "type": "concept"}, {"label": "B", "type": "concept"}],
        "relations": [{"source": "A", "target": "B", "relation": "NONSENSE"}],
    }
    _, edges, warnings = normalize_graph(payload, "doc_1", [_chunk("c1", "A and B")])
    assert edges == []
    assert any("invalid relation" in w for w in warnings)


def test_normalize_contradictory_edges_both_preserved():
    chunks = [_chunk("c1", "Consolidation supports and also contradicts memory claims.")]
    payload = {
        "concepts": [
            {"label": "Consolidation", "type": "concept"},
            {"label": "Memory", "type": "concept"},
        ],
        "relations": [
            {"source": "Consolidation", "target": "Memory", "relation": "SUPPORTS"},
            {"source": "Consolidation", "target": "Memory", "relation": "CONTRADICTS"},
        ],
    }
    _, edges, _ = normalize_graph(payload, "doc_1", chunks)
    relations = {(e.relation, e.source, e.target) for e in edges}
    assert (GraphEdgeType.SUPPORTS, "concept:consolidation", "concept:memory") in relations
    assert (GraphEdgeType.CONTRADICTS, "concept:consolidation", "concept:memory") in relations
    assert all(not e.is_inference for e in edges)  # both traceable to evidence


def test_normalize_marks_unattributed_edge_as_inference():
    chunks = [_chunk("c1", "Only consolidation is mentioned here.")]
    payload = {
        "concepts": [
            {"label": "Consolidation", "type": "concept"},
            {"label": "Memory", "type": "concept"},
        ],
        "relations": [{"source": "Consolidation", "target": "Memory", "relation": "CAUSES"}],
    }
    _, edges, _ = normalize_graph(payload, "doc_1", chunks)
    assert edges[0].is_inference is True
    assert edges[0].source_chunks == []


def test_normalize_ambiguous_same_label_different_type():
    payload = {
        "concepts": [
            {"label": "Sleep", "type": "concept"},
            {"label": "Sleep", "type": "event"},
        ],
        "relations": [],
    }
    nodes, _, _ = normalize_graph(payload, "doc_1", [_chunk("c1", "Sleep event and concept.")])
    assert len(nodes) == 2
    assert {n.id for n in nodes} == {"concept:sleep", "event:sleep"}


def test_normalize_multi_page_node():
    chunks = [
        _chunk("c1", "Memory is encoded.", page=1),
        _chunk("c2", "Memory is consolidated.", page=3),
    ]
    payload = {"concepts": [{"label": "Memory", "type": "concept"}], "relations": []}
    nodes, _, _ = normalize_graph(payload, "doc_1", chunks)
    assert nodes[0].page_numbers == [1, 3]
    assert set(nodes[0].source_chunks) == {"c1", "c2"}


def test_extract_graph_with_stub_provider(tmp_path):
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/g.db"))
    settings.llm.provider = "stub"
    engine = build_engine(settings)
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        session.add(
            Document(
                id="doc_1",
                title="Search Book",
                original_filename="b.pdf",
                sha256="a" * 64,
                file_size=1,
            )
        )
        session.flush()
        session.add_all(
            [
                _chunk(
                    "c1",
                    "Memory is the faculty for encoding, storing and retrieving information.",
                    1,
                ),
                _chunk("c2", "Consolidation stabilises memories and improves recall accuracy.", 3),
                _chunk("c3", "Retrieval cues improve recall accuracy.", 4),
            ]
        )
        session.flush()
        nodes, edges, warnings = extract_graph(session, settings, session.get(Document, "doc_1"))

    labels = {n.label for n in nodes}
    assert labels == {"Memory", "Consolidation", "Retrieval cues", "Researchers"}
    assert "Memory" in labels
    # duplicate Memory merged into one node
    assert len([n for n in nodes if n.label == "Memory"]) == 1
    # duplicate edge dropped -> Consolidation->Memory and Retrieval cues->Memory
    assert len(edges) == 2
    consolidation_edge = next(e for e in edges if e.source.endswith("consolidation"))
    assert consolidation_edge.is_inference is False  # traceable to evidence
    assert consolidation_edge.source_chunks
    assert any(n.source_chunks for n in nodes)


def test_extract_graph_invalid_json(tmp_path):
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/g2.db"))
    settings.llm.provider = "stub"
    engine = build_engine(settings)
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        session.add(
            Document(id="doc_1", title="x", original_filename="b.pdf", sha256="a" * 64, file_size=1)
        )
        session.flush()
        session.add(_chunk("c1", "Memory is encoded."))
        session.flush()

        from mindweaver.graph import extractor as extractor_module

        original = extractor_module.get_llm_provider

        class BrokenStub(StubLLMProvider):
            def complete(self, messages, **kwargs):
                return "not json at all"

        extractor_module.get_llm_provider = lambda settings: BrokenStub()  # type: ignore[assignment]
        try:
            with pytest.raises(GraphExtractionError):
                extract_graph(session, settings, session.get(Document, "doc_1"))
        finally:
            extractor_module.get_llm_provider = original
