"""Mind map generation.

The initial map is deliberately shallow and bounded: Document -> Main Topics
(chapters) -> Key Concepts (top graph concepts per topic). High-value concepts
are chosen by graph degree; weak-hierarchy documents fall back to graph
concepts as topics.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver.chunking.service import list_chunks
from mindweaver.config import MindMapConfig, Settings
from mindweaver.document_model import CanonicalDocument
from mindweaver.graph.types import GraphNode, GraphNodeType, GraphRead
from mindweaver.mindmap.types import MindMap, MindMapNode, NodeSourceInfo
from mindweaver.models import ChunkRecord, Document, MindMapPreferencesRecord


def _degree(graph: GraphRead) -> dict[str, int]:
    degree: dict[str, int] = defaultdict(int)
    for edge in graph.edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
    return degree


def _chunk_chapter_map(chunks: list[ChunkRecord]) -> dict[str, str | None]:
    return {chunk.chunk_id: _section_path0(chunk.section_path) for chunk in chunks}


def _section_path0(value: str) -> str | None:
    import json

    try:
        path = json.loads(value)
        return path[0] if path else None
    except Exception:
        return None


def _topic_nodes_from_sections(canonical: CanonicalDocument) -> list[MindMapNode]:
    topics: list[MindMapNode] = []
    for section in canonical.sections:
        if section.level != 1:
            continue
        topics.append(
            MindMapNode(
                id=f"topic:{_stable(section.title)}",
                label=section.title,
                node_type="topic",
                depth=1,
                source=NodeSourceInfo(
                    section_path=section.section_path,
                    pages=_pages_from_sections(section),
                ),
            )
        )
    return topics


def _pages_from_sections(section: Any) -> list[int]:
    pages = {section.page_number}
    for child in section.children:
        pages.add(child.page_number)
    return sorted(page for page in pages if page)


def _stable(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:48].rstrip("-") or "unknown"


def _concepts_for_topic(
    topic_title: str,
    graph: GraphRead,
    chunk_chapter_map: dict[str, str | None],
    degree: dict[str, int],
    limit: int,
    used: set[str],
) -> list[GraphNode]:
    """Top concepts whose source chunks fall under this chapter."""

    candidates: list[GraphNode] = []
    for node in graph.nodes:
        if node.id in used or node.type.value not in ("concept", "topic"):
            continue
        belongs = any(
            chunk_chapter_map.get(chunk_id) == topic_title for chunk_id in node.source_chunks
        )
        if belongs:
            candidates.append(node)
    candidates.sort(key=lambda node: degree.get(node.id, 0), reverse=True)
    return candidates[:limit]


def _build_concept_node(node: GraphNode, degree: dict[str, int], depth: int) -> MindMapNode:
    return MindMapNode(
        id=node.id,
        label=node.label,
        node_type=node.type.value,
        depth=depth,
        source=NodeSourceInfo(
            graph_node_id=node.id,
            chunk_ids=node.source_chunks,
            pages=node.page_numbers,
            is_inference=False,
        ),
        meta={"degree": degree.get(node.id, 0)},
    )


def build_mindmap(
    document: Document,
    canonical: CanonicalDocument | None,
    graph: GraphRead | None,
    config: MindMapConfig,
    chunk_chapter_map: dict[str, str | None] | None = None,
) -> MindMap:
    root = MindMapNode(
        id=f"doc:{document.id}",
        label=document.title or document.original_filename,
        node_type="root",
        depth=0,
    )

    topic_nodes: list[MindMapNode] = []
    if canonical is not None:
        topic_nodes = _topic_nodes_from_sections(canonical)[: config.max_topics]

    used: set[str] = set()
    if graph is not None:
        degree = _degree(graph)
        if topic_nodes:
            # Attach high-value concepts to their chapters.
            for topic in topic_nodes:
                concepts = _concepts_for_topic(
                    topic.label,
                    graph,
                    chunk_chapter_map or {},
                    degree,
                    config.max_concepts_per_topic,
                    used,
                )
                for node in concepts:
                    used.add(node.id)
                    topic.children.append(_build_concept_node(node, degree, 2))
        else:
            # Weak hierarchy: top concepts become the topics.
            ranked = sorted(
                (node for node in graph.nodes if node.type.value in ("concept", "topic")),
                key=lambda node: degree.get(node.id, 0),
                reverse=True,
            )
            for node in ranked[: config.max_topics]:
                used.add(node.id)
                topic = MindMapNode(
                    id=node.id,
                    label=node.label,
                    node_type="topic",
                    depth=1,
                    source=NodeSourceInfo(
                        graph_node_id=node.id,
                        chunk_ids=node.source_chunks,
                        pages=node.page_numbers,
                    ),
                )
                neighbours = sorted(
                    (
                        graph_node
                        for graph_node in graph.nodes
                        if graph_node.id != node.id and _is_neighbour(node.id, graph_node.id, graph)
                    ),
                    key=lambda candidate: degree.get(candidate.id, 0),
                    reverse=True,
                )
                for neighbour in neighbours[: config.max_concepts_per_topic]:
                    if neighbour.id in used:
                        continue
                    used.add(neighbour.id)
                    topic.children.append(_build_concept_node(neighbour, degree, 2))
                topic_nodes.append(topic)

    root.children = topic_nodes
    total = _count_nodes(root)
    return MindMap(
        document_id=document.id,
        root=root,
        total_nodes=total,
        max_depth=config.max_depth,
    )


def _is_neighbour(a: str, b: str, graph: GraphRead) -> bool:
    return any({edge.source, edge.target} == {a, b} for edge in graph.edges)


def _count_nodes(node: MindMapNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def generate_mindmap(session: Session, settings: Settings, document: Document) -> MindMap | None:
    from mindweaver.chunking.service import load_canonical_document
    from mindweaver.graph.service import get_graph

    canonical = load_canonical_document(settings, document.id)
    graph = get_graph(session, document.id)
    chunk_chapter_map = _chunk_chapter_map(list_chunks(session, document.id))
    return build_mindmap(
        document, canonical, graph, settings.mindmap, chunk_chapter_map=chunk_chapter_map
    )


def find_view_node(root: MindMapNode, node_id: str) -> MindMapNode | None:
    """Depth-first search for ``node_id`` in the mind map view tree."""
    if root.id == node_id:
        return root
    for child in root.children:
        found = find_view_node(child, node_id)
        if found is not None:
            return found
    return None


def resolve_action_node(
    session: Session,
    settings: Settings,
    document: Document,
    node_id: str,
) -> GraphNode | None:
    """Resolve ``node_id`` to an actionable node.

    Knowledge-graph nodes win. Structural mind-map nodes (``topic:<slug>``,
    ``doc:<id>``) exist only in the view — never in the graph — so they are
    wrapped in a synthetic graph node whose source chunks come from the view
    metadata or, failing that, a label search (documents with weak section
    provenance have no chapter mapping to lean on).
    """
    from mindweaver.graph.service import get_graph
    from mindweaver.search.service import search

    graph = get_graph(session, document.id)
    if graph is not None:
        for node in graph.nodes:
            if node.id == node_id:
                return node

    mindmap = generate_mindmap(session, settings, document)
    if mindmap is None:
        return None
    view_node = find_view_node(mindmap.root, node_id)
    if view_node is None:
        return None

    chunks = list_chunks(session, document.id)
    chunk_ids = list(view_node.source.chunk_ids) if view_node.source else []
    if not chunk_ids:
        retrieved = search(
            session,
            settings,
            view_node.label,
            document_id=document.id,
            limit=max(settings.chat.evidence_limit, 5),
        )
        chunk_ids = [hit.chunk_id for hit in retrieved.results]

    pages = set(view_node.source.pages) if view_node.source else set()
    for chunk in chunks:
        if chunk.chunk_id in chunk_ids:
            pages.update(range(chunk.page_start, chunk.page_end + 1))

    return GraphNode(
        id=view_node.id,
        label=view_node.label,
        type=GraphNodeType.TOPIC,
        source_chunks=chunk_ids,
        page_numbers=sorted(pages),
    )


def get_preferences(session: Session, document_id: str) -> dict[str, Any]:
    record = session.scalar(
        select(MindMapPreferencesRecord).where(MindMapPreferencesRecord.document_id == document_id)
    )
    if record is None:
        return {}
    try:
        return cast(dict[str, Any], json.loads(record.layout))
    except Exception:
        return {}


def set_preferences(session: Session, document_id: str, layout: dict[str, Any]) -> None:
    record = session.scalar(
        select(MindMapPreferencesRecord).where(MindMapPreferencesRecord.document_id == document_id)
    )
    if record is None:
        session.add(
            MindMapPreferencesRecord(
                document_id=document_id,
                layout=json.dumps(layout),
            )
        )
    else:
        record.layout = json.dumps(layout)
    session.flush()
