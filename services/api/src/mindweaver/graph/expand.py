"""Interactive mind map node expansion.

Expanding a node retrieves its source chunks plus additional evidence, asks
the LLM for new concepts/relations, validates + deduplicates, and merges the
result into the graph (versioned). Expansion is atomic: a failed or cancelled
LLM call leaves the graph unchanged.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from mindweaver.chunking.service import list_chunks
from mindweaver.config import Settings
from mindweaver.graph.extractor import GraphExtractionError, normalize_graph
from mindweaver.graph.service import append_graph, get_graph
from mindweaver.graph.types import GraphEdge, GraphNode
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.service import search


class NodeNotFoundError(Exception):
    pass


SYSTEM_PROMPT = (
    "You expand a knowledge graph around a focus node. Use the same node types "
    "(concept, claim, event, person, topic) and relations (EXPLAINS, CAUSES, "
    "AFFECTS, SUPPORTS, CONTRADICTS, PART_OF, RELATED_TO, PRECEDES, FOLLOWS, "
    "EXAMPLE_OF) as before.\n"
    'Respond with JSON only: {"concepts": [{"label", "type", "definition"}], '
    '"relations": [{"source", "target", "relation", "note"}]}.\n'
    "Only add concepts and relations that appear in the evidence. Do not "
    "duplicate concepts that are already in the graph."
)


def _numbered_chunks(chunks: list[ChunkRecord]) -> str:
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{index}] (pages={chunk.page_start}-{chunk.page_end})\n{chunk.text}")
    return "\n\n".join(blocks)


def build_expand_messages(node: GraphNode, chunks: list[ChunkRecord]) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=(
                f"Expand a knowledge graph around the focus node: "
                f"{node.label} (type {node.type.value}).\n\n"
                f"Evidence:\n\n{_numbered_chunks(chunks)}"
            ),
        ),
    ]


def expand_node(
    session: Session, settings: Settings, document: Document, node_id: str
) -> tuple[list[GraphNode], list[GraphEdge], list[str], int]:
    """Expand ``node_id`` and merge new concepts/relations into the graph.

    Returns ``(added_nodes, added_edges, warnings, graph_version)``. Raises
    :class:`NodeNotFoundError` for unknown nodes and :class:`GraphExtractionError`
    when the LLM output cannot be parsed (nothing is written).
    """
    graph = get_graph(session, document.id)
    if graph is None:
        raise NodeNotFoundError(node_id)
    node = next((n for n in graph.nodes if n.id == node_id), None)
    if node is None:
        # Structural mind-map nodes (topic:<slug>, doc:<id>) exist only in the
        # view, not in the graph — resolve them through the mind map service.
        from mindweaver.mindmap.service import resolve_action_node

        node = resolve_action_node(session, settings, document, node_id)
    if node is None:
        raise NodeNotFoundError(node_id)

    chunks = list_chunks(session, document.id)
    node_chunks = [chunk for chunk in chunks if chunk.chunk_id in node.source_chunks]

    retrieved = search(session, settings, node.label, document_id=document.id, limit=5)
    retrieved_ids = {hit.chunk_id for hit in retrieved.results}
    context = node_chunks + [
        chunk for chunk in chunks if chunk.chunk_id in retrieved_ids and chunk not in node_chunks
    ]

    provider = get_llm_provider(settings)
    raw = provider.complete(
        build_expand_messages(node, context),
        temperature=settings.llm.temperature,
        max_tokens=settings.graph.max_tokens,
    )
    payload = extract_json(raw)
    if payload is None:
        raise GraphExtractionError("LLM returned invalid JSON for node expansion")

    known_labels = {existing.label.lower(): [existing.id] for existing in graph.nodes}
    existing_ids = {existing.id for existing in graph.nodes}
    existing_edges = {(edge.source, edge.target, edge.relation.value) for edge in graph.edges}
    if node.id not in existing_ids:
        # Focus node came from the mind map view; make its label resolvable
        # so LLM relations can anchor onto it.
        known_labels.setdefault(node.label.lower(), []).insert(0, node.id)

    new_nodes, new_edges, warnings = normalize_graph(
        payload, document.id, context, known_labels=known_labels
    )

    added_nodes = [candidate for candidate in new_nodes if candidate.id not in existing_ids]
    added_edges = [
        candidate
        for candidate in new_edges
        if (candidate.source, candidate.target, candidate.relation.value) not in existing_edges
    ]

    # Referential integrity: persist the view-resolved focus node when new
    # edges anchor onto it; drop edges that still reference unknown nodes.
    resolved_ids = {existing.id for existing in graph.nodes} | {
        candidate.id for candidate in added_nodes
    }
    unresolved = {
        endpoint
        for edge in added_edges
        for endpoint in (edge.source, edge.target)
        if endpoint not in resolved_ids
    }
    for unknown_id in sorted(unresolved):
        if unknown_id == node.id:
            added_nodes.insert(0, node)
            resolved_ids.add(node.id)
    kept_edges: list[GraphEdge] = []
    for edge in added_edges:
        if edge.source in resolved_ids and edge.target in resolved_ids:
            kept_edges.append(edge)
        else:
            warnings.append(
                f"edge {edge.source} -{edge.relation.value}-> {edge.target} "
                "dropped: unknown endpoint"
            )
    added_edges = kept_edges

    version = graph.version
    if added_nodes or added_edges:
        version = append_graph(
            session, document, added_nodes, added_edges, warnings, operation="expand"
        )

    return added_nodes, added_edges, warnings, version
