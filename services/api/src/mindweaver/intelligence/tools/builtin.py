"""Built-in read-only tools backed by existing MindWeaver services."""

from __future__ import annotations

import json
from typing import Any

from mindweaver.graph.service import get_graph
from mindweaver.intelligence.tools.registry import ToolContext, ToolError, ToolRegistry, ToolSpec


def _search_document(context: ToolContext, query: str = "", limit: int = 5) -> dict[str, Any]:
    from mindweaver.search.service import search as run_search

    response = run_search(
        context.session,
        context.settings,
        query,
        document_ids=list(context.document_ids),
        with_labels=True,
        limit=max(1, min(int(limit), 20)),
    )
    return {
        "results": [
            {
                "document_id": hit.document_id,
                "source_label": hit.source_label,
                "chunk_id": hit.chunk_id,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "section": " / ".join(hit.section_path),
                "text": hit.text[:600],
                "score": round(hit.retrieval_score, 4),
            }
            for hit in response.results
        ]
    }


def _get_chunk(context: ToolContext, chunk_id: str = "") -> dict[str, Any]:
    from mindweaver.chunking.service import list_chunks

    allowed = set(context.document_ids)
    for document_id in context.document_ids:
        for record in list_chunks(context.session, document_id):
            if record.chunk_id == chunk_id and record.document_id in allowed:
                return {
                    "chunk_id": record.chunk_id,
                    "document_id": record.document_id,
                    "pages": [record.page_start, record.page_end],
                    "section": " / ".join(
                        json.loads(record.section_path) if record.section_path else []
                    ),
                    "text": record.text[:1500],
                }
    raise ToolError(f"chunk not found in scope: {chunk_id}")


def _get_page(context: ToolContext, document_id: str = "", page_number: int = 1) -> dict[str, Any]:
    context.assert_document(document_id)
    from mindweaver import storage
    from mindweaver.chunking.service import list_chunks
    from mindweaver.models import Document

    document = context.session.get(Document, document_id)
    if document is None:
        raise ToolError(f"document not found: {document_id}")
    page_number = max(1, int(page_number))
    if document.page_count and page_number > document.page_count:
        raise ToolError(f"page {page_number} out of range")

    page_text: list[str] = []
    chunks_for_doc = list_chunks(context.session, document_id)
    for chunk_record in chunks_for_doc:
        if chunk_record.page_start <= page_number <= chunk_record.page_end:
            body = chunk_record.text.split("\n\n", 1)[-1]
            page_text.append(body[:400])
    canonical = storage.load_derived_json(context.settings, document_id, "canonical.json")
    image_available = False
    if isinstance(canonical, dict):
        for block in (
            canonical.get("blocks", []) if isinstance(canonical.get("blocks"), list) else []
        ):
            if block.get("page_number") == page_number:
                image_available = True  # block provenance exists; raw bytes stay internal
                break
    return {
        "document_id": document_id,
        "page_number": page_number,
        "text": "\n".join(page_text)[:1200],
        "image_reference": "available via Open PDF" if image_available else None,
    }


def _get_graph_node(context: ToolContext, node_id: str = "") -> dict[str, Any]:
    from mindweaver.graph.service import get_graph

    wanted = node_id.strip()
    for document_id in context.document_ids:
        graph = get_graph(context.session, document_id)
        if graph is None:
            continue
        for node in graph.nodes:
            if node.id == wanted or node.label.lower() == wanted.lower():
                return node.model_dump()
    raise ToolError(f"node not found in scope: {node_id}")


def _get_graph_neighbors(context: ToolContext, node_id: str = "", depth: int = 1) -> dict[str, Any]:
    depth = max(1, min(int(depth), 2))
    resolved: set[str] = set()
    for document_id in context.document_ids:
        graph = get_graph(context.session, document_id)
        if graph is None:
            continue
        for node in graph.nodes:
            if node.id == node_id or node.label.lower() == node_id.strip().lower():
                resolved.add(node.id)
    frontier = resolved or {node_id}
    neighbours: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for document_id in context.document_ids:
        graph = get_graph(context.session, document_id)
        if graph is None:
            continue
        current = set(frontier)
        for _ in range(depth):
            nxt: set[str] = set()
            for edge in graph.edges:
                pair = (edge.source, edge.target, edge.relation.value)
                if pair in seen_edges:
                    continue
                seen_edges.add(pair)
                if edge.source in current or edge.target in current:
                    relations.append(
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "relation": edge.relation.value,
                        }
                    )
                    nxt.add(edge.source)
                    nxt.add(edge.target)
            current = nxt - set(frontier)
            frontier |= current

    for doc_id in context.document_ids:
        graph = get_graph(context.session, doc_id)
        if graph is None:
            continue
        for node in graph.nodes:
            if node.id in frontier and node.id != node_id and node.id not in neighbours:
                neighbours[node.id] = {"id": node.id, "label": node.label}

    return {"neighbours": list(neighbours.values()), "relations": relations}


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="search_document",
            description="Search the current documents for relevant passages.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        _search_document,
    )
    registry.register(
        ToolSpec(
            name="get_chunk",
            description="Return one stored text chunk by id.",
            parameters={
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}},
                "required": ["chunk_id"],
            },
        ),
        _get_chunk,
    )
    registry.register(
        ToolSpec(
            name="get_page",
            description="Return the text of one PDF page plus metadata.",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "page_number": {"type": "integer", "default": 1},
                },
                "required": ["document_id"],
            },
        ),
        _get_page,
    )
    registry.register(
        ToolSpec(
            name="get_graph_node",
            description=(
                "Return one knowledge-graph node. Use the exact node id "
                "(e.g. 'concept:memory') from list_graph_nodes or the expansion request."
            ),
            parameters={
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
        _get_graph_node,
    )
    registry.register(
        ToolSpec(
            name="get_graph_neighbors",
            description="Return the neighbours of a knowledge-graph node.",
            parameters={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "depth": {"type": "integer", "default": 1},
                },
                "required": ["node_id"],
            },
        ),
        _get_graph_neighbors,
    )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry
