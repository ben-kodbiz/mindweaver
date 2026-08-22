from mindweaver.config import MindMapConfig
from mindweaver.document_model import CanonicalDocument, ContentBlock, Page, Section
from mindweaver.graph.types import GraphEdge, GraphNode, GraphNodeType, GraphRead
from mindweaver.mindmap.service import build_mindmap
from mindweaver.models import Document


def _document() -> Document:
    return Document(
        id="doc_1", title="Search Book", original_filename="b.pdf", sha256="a" * 64, file_size=1
    )


def _canonical(chapters: int = 4, sections_per_chapter: int = 2) -> CanonicalDocument:
    sections: list[Section] = []
    blocks: list[ContentBlock] = []
    for chapter in range(1, chapters + 1):
        chapter_section = Section(
            id=f"sec_ch{chapter}",
            title=f"Chapter {chapter}",
            level=1,
            page_number=chapter,
            section_path=[f"Chapter {chapter}"],
        )
        for section in range(1, sections_per_chapter + 1):
            chapter_section.children.append(
                Section(
                    id=f"sec_ch{chapter}_s{section}",
                    title=f"Section {chapter}.{section}",
                    level=2,
                    page_number=chapter,
                    section_path=[f"Chapter {chapter}", f"Section {chapter}.{section}"],
                )
            )
        sections.append(chapter_section)
        blocks.append(
            ContentBlock(
                block_id=f"blk_{chapter}",
                document_id="doc_1",
                page_number=chapter,
                block_type="paragraph",
                text=f"Content in chapter {chapter}.",
                section_path=[f"Chapter {chapter}"],
            )
        )
    return CanonicalDocument(
        document_id="doc_1",
        source_filename="b.pdf",
        processor="pypdf",
        pages=[Page(page_number=i + 1) for i in range(chapters)],
        sections=sections,
        blocks=blocks,
    )


def _graph(chapters: int = 4, concepts_per_chapter: int = 5) -> GraphRead:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for chapter in range(1, chapters + 1):
        for concept in range(1, concepts_per_chapter + 1):
            node_id = f"concept:c{chapter}k{concept}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=f"Concept {chapter}.{concept}",
                    type=GraphNodeType.CONCEPT,
                    source_chunks=[f"chunk_{chapter}"],
                    page_numbers=[chapter],
                )
            )
            if concept > 1:
                edges.append(
                    GraphEdge(
                        source=f"concept:c{chapter}k{concept}",
                        target=f"concept:c{chapter}k1",
                        relation="related_to",
                        source_chunks=[f"chunk_{chapter}"],
                    )
                )
    return GraphRead(document_id="doc_1", version=1, nodes=nodes, edges=edges)


def _chunk_chapter_map(chapters: int) -> dict[str, str | None]:
    return {f"chunk_{c}": f"Chapter {c}" for c in range(1, chapters + 1)}


def test_bounded_initial_map():
    config = MindMapConfig(max_topics=3, max_concepts_per_topic=2, max_depth=2)
    mindmap = build_mindmap(
        _document(),
        _canonical(chapters=6),
        _graph(chapters=6),
        config,
        chunk_chapter_map=_chunk_chapter_map(6),
    )
    assert mindmap.root.label == "Search Book"
    assert mindmap.root.node_type == "root"
    # topics limited
    assert len(mindmap.root.children) == 3
    # each topic has at most max_concepts_per_topic concepts
    for topic in mindmap.root.children:
        assert topic.depth == 1
        assert len(topic.children) <= 2
        for concept in topic.children:
            assert concept.depth == 2
    assert mindmap.total_nodes == 1 + 3 + sum(len(t.children) for t in mindmap.root.children)
    assert mindmap.total_nodes <= 10


def test_concepts_attributed_to_correct_chapter():
    config = MindMapConfig(max_topics=10, max_concepts_per_topic=3, max_depth=2)
    mindmap = build_mindmap(
        _document(),
        _canonical(chapters=2),
        _graph(chapters=2),
        config,
        chunk_chapter_map=_chunk_chapter_map(2),
    )
    by_label = {topic.label: topic for topic in mindmap.root.children}
    chapter1 = by_label["Chapter 1"]
    assert all(concept.label.startswith("Concept 1.") for concept in chapter1.children)
    chapter2 = by_label["Chapter 2"]
    assert all(concept.label.startswith("Concept 2.") for concept in chapter2.children)


def test_high_value_concepts_selected_by_degree():
    config = MindMapConfig(max_topics=1, max_concepts_per_topic=2, max_depth=2)
    mindmap = build_mindmap(
        _document(),
        _canonical(chapters=1),
        _graph(chapters=1, concepts_per_chapter=5),
        config,
        chunk_chapter_map=_chunk_chapter_map(1),
    )
    topic = mindmap.root.children[0]
    # c1k1 has the highest degree (connected to all others); it should be first
    assert topic.children[0].label == "Concept 1.1"


def test_weak_hierarchy_falls_back_to_concepts():
    config = MindMapConfig(max_topics=3, max_concepts_per_topic=2, max_depth=2)
    mindmap = build_mindmap(_document(), None, _graph(chapters=2), config)
    assert len(mindmap.root.children) <= 3
    for topic in mindmap.root.children:
        assert topic.node_type == "topic"
        assert topic.depth == 1


def test_source_metadata_attached_invisibly():
    config = MindMapConfig(max_topics=4, max_concepts_per_topic=2, max_depth=2)
    mindmap = build_mindmap(
        _document(),
        _canonical(chapters=2),
        _graph(chapters=2),
        config,
        chunk_chapter_map=_chunk_chapter_map(2),
    )
    topic = mindmap.root.children[0]
    concept = topic.children[0]
    assert concept.source is not None
    assert concept.source.graph_node_id == concept.id
    assert concept.source.chunk_ids
    assert concept.source.pages
    assert topic.source is not None
    assert topic.source.section_path


def test_no_graph_still_produces_topics():
    config = MindMapConfig(max_topics=4, max_concepts_per_topic=2, max_depth=2)
    mindmap = build_mindmap(_document(), _canonical(chapters=3), None, config)
    assert len(mindmap.root.children) == 3
    assert mindmap.total_nodes == 4
