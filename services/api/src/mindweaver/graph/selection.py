"""Add a PDF text selection to the mind map.

The selected text is fed to the LLM which proposes concepts/relations; the
client confirms, and only then are the candidates merged into the graph
(versioned). Nothing is written before confirmation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.graph.extractor import (
    SYSTEM_PROMPT as GRAPH_SYSTEM_PROMPT,
)
from mindweaver.graph.extractor import (
    GraphExtractionError,
    normalize_graph,
)
from mindweaver.graph.service import append_graph, get_graph
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.models import ChunkRecord, Document

SYSTEM_PROMPT = GRAPH_SYSTEM_PROMPT + (
    "\nExtract concepts and relationships from the following selection of text "
    "(a selection is a short excerpt the user chose in the PDF)."
)


def _selection_chunk(document_id: str, text: str, page_number: int) -> ChunkRecord:
    return ChunkRecord(
        chunk_id="__selection__",
        document_id=document_id,
        position=0,
        page_start=page_number,
        page_end=page_number,
        chapter=None,
        section=None,
        subsection=None,
        section_path="[]",
        text=text,
        token_count=len(text.split()),
        parent_chunk_id=None,
    )


def extract_selection(
    session: Session,
    settings: Settings,
    document: Document,
    text: str,
    page_number: int,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    chunk = _selection_chunk(document.id, text, page_number)
    provider = get_llm_provider(settings)
    raw = provider.complete(
        [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    f"Extract concepts and relationships from the following selection.\n\n{text}"
                ),
            ),
        ],
        temperature=settings.llm.temperature,
        max_tokens=settings.graph.max_tokens,
    )
    payload = extract_json(raw)
    if payload is None:
        raise GraphExtractionError("LLM returned invalid JSON for the selection")

    graph = get_graph(session, document.id)
    known_labels = (
        {node.label.lower(): [node.id] for node in graph.nodes} if graph is not None else {}
    )
    nodes, edges, warnings = normalize_graph(
        payload, document.id, [chunk], known_labels=known_labels
    )

    existing_ids = {node.id for node in graph.nodes} if graph is not None else set()
    existing_edges = (
        {(edge.source, edge.target, edge.relation.value) for edge in graph.edges}
        if graph is not None
        else set()
    )
    new_nodes = [node for node in nodes if node.id not in existing_ids]
    new_edges = [
        edge
        for edge in edges
        if (edge.source, edge.target, edge.relation.value) not in existing_edges
    ]

    added = False
    if confirm and (new_nodes or new_edges):
        append_graph(session, document, new_nodes, new_edges, warnings, operation="selection")
        added = True

    return {
        "candidates": {
            "nodes": [node.model_dump() for node in new_nodes],
            "edges": [edge.model_dump() for edge in new_edges],
        },
        "added": added,
        "warnings": warnings,
    }
