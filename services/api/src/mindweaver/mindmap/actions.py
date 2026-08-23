"""Mind map node actions: expand, explain, evidence, related, ask."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mindweaver.chat.rag import answer_question
from mindweaver.chat.types import AnswerResult
from mindweaver.config import Settings
from mindweaver.graph.expand import NodeNotFoundError
from mindweaver.graph.expand import expand_node as _expand_node
from mindweaver.graph.service import get_graph
from mindweaver.graph.types import GraphNode
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.mindmap.service import generate_mindmap, resolve_action_node
from mindweaver.mindmap.types import (
    EvidenceChunk,
    ExpandResult,
    ExplainResult,
    NodeEvidence,
    RelatedNode,
)
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.base import SearchHit
from mindweaver.search.service import search


def _find_node(session: Session, settings: Settings, document: Document, node_id: str) -> GraphNode:
    node = resolve_action_node(session, settings, document, node_id)
    if node is None:
        raise NodeNotFoundError(node_id)
    return node


def _node_chunks(session: Session, document_id: str, node: GraphNode) -> list[ChunkRecord]:
    from mindweaver.chunking.service import list_chunks

    chunks = list_chunks(session, document_id)
    return [chunk for chunk in chunks if chunk.chunk_id in node.source_chunks]


def expand_node(
    session: Session, settings: Settings, document: Document, node_id: str
) -> ExpandResult:
    added_nodes, added_edges, warnings, version = _expand_node(session, settings, document, node_id)
    mindmap = generate_mindmap(session, settings, document)
    return ExpandResult(
        node_id=node_id,
        added_nodes=[node.model_dump() for node in added_nodes],
        added_edges=[edge.model_dump() for edge in added_edges],
        warnings=warnings,
        graph_version=version,
        mindmap=mindmap,
    )


EXPLAIN_SYSTEM = (
    "You explain a concept using only the provided evidence. Respond with JSON only: "
    '{"explanation": "...", "grounding": "supported_by_source|inference|not_found", '
    '"citations": [<evidence numbers>]}. Cite evidence by number; never invent facts.'
)


def _chunk_to_evidence(chunks: list[ChunkRecord]) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for chunk in chunks:
        import json as _json

        try:
            section_path = _json.loads(chunk.section_path)
        except Exception:
            section_path = []
        hits.append(
            SearchHit(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_path=section_path,
                text=chunk.text,
                retrieval_score=0.0,
            )
        )
    return hits


def explain_node(
    session: Session, settings: Settings, document: Document, node_id: str
) -> ExplainResult:
    node = _find_node(session, settings, document, node_id)
    node_chunks = _node_chunks(session, document.id, node)

    related = _related_concepts(session, settings, document, node)

    blocks = []
    for index, chunk in enumerate(node_chunks, start=1):
        blocks.append(f"[{index}] (pages={chunk.page_start}-{chunk.page_end})\n{chunk.text}")
    if not blocks:
        return ExplainResult(
            node_id=node_id,
            label=node.label,
            explanation="No source evidence is available for this node.",
            grounding="not_found",
            citations=[],
            related_concepts=related,
        )

    provider = get_llm_provider(settings)
    raw = provider.complete(
        [
            LLMMessage(role="system", content=EXPLAIN_SYSTEM),
            LLMMessage(
                role="user",
                content=(
                    f"Explain the concept '{node.label}' using the following evidence.\n\n"
                    f"{chr(10).join(blocks)}\n\nConcept: {node.label}"
                ),
            ),
        ],
        temperature=settings.llm.temperature,
        max_tokens=settings.chat.max_tokens,
    )
    payload = extract_json(raw) or {}
    explanation = str(payload.get("explanation") or "").strip()
    grounding = payload.get("grounding")
    if grounding not in ("supported_by_source", "inference", "not_found"):
        grounding = "inference"
    citations = []
    for item in payload.get("citations") or []:
        try:
            index = int(item) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(node_chunks):
            chunk = node_chunks[index]
            citations.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section": _json_path0(chunk.section_path),
                }
            )
    return ExplainResult(
        node_id=node_id,
        label=node.label,
        explanation=explanation or "No explanation was generated.",
        grounding=grounding,
        citations=citations,
        related_concepts=related,
    )


def _json_path0(value: str) -> str | None:
    import json

    try:
        path = json.loads(value)
        return path[0] if path else None
    except Exception:
        return None


def node_evidence(
    session: Session, settings: Settings, document: Document, node_id: str
) -> NodeEvidence:
    node = _find_node(session, settings, document, node_id)
    node_chunks = _node_chunks(session, document.id, node)
    pages = sorted(
        {page for chunk in node_chunks for page in range(chunk.page_start, chunk.page_end + 1)}
    ) or list(node.page_numbers)
    return NodeEvidence(
        node_id=node_id,
        label=node.label,
        pages=pages,
        chunks=[
            EvidenceChunk(
                chunk_id=chunk.chunk_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_path=_json_loads(chunk.section_path),
                text=chunk.text,
            )
            for chunk in node_chunks
        ],
    )


def _json_loads(value: str) -> list[str]:
    import json
    from typing import cast

    try:
        return cast(list[str], json.loads(value))
    except Exception:
        return []


def related_nodes(
    session: Session, settings: Settings, document: Document, node_id: str
) -> list[RelatedNode]:
    node = _find_node(session, settings, document, node_id)
    return _related_concepts(session, settings, document, node)


def _related_concepts(
    session: Session, settings: Settings, document: Document, node: GraphNode
) -> list[RelatedNode]:
    graph = get_graph(session, document.id)
    result: list[RelatedNode] = []
    seen: set[str] = set()

    if graph is not None:
        for edge in graph.edges:
            relation = None
            neighbour_id = None
            if edge.source == node.id:
                neighbour_id, relation = edge.target, edge.relation.value
            elif edge.target == node.id:
                neighbour_id, relation = edge.source, edge.relation.value
            if neighbour_id is None or neighbour_id in seen:
                continue
            neighbour = next((n for n in graph.nodes if n.id == neighbour_id), None)
            if neighbour is None:
                continue
            seen.add(neighbour_id)
            result.append(
                RelatedNode(node_id=neighbour_id, label=neighbour.label, relation=relation)
            )

    # Semantic neighbours: search for the node label; match graph nodes whose
    # source chunks appear in the results.
    retrieved = search(session, settings, node.label, document_id=document.id, limit=5)
    hit_chunks = {hit.chunk_id for hit in retrieved.results}
    for graph_node in graph.nodes if graph is not None else []:
        if graph_node.id in seen or graph_node.id == node.id:
            continue
        if any(chunk_id in hit_chunks for chunk_id in graph_node.source_chunks):
            seen.add(graph_node.id)
            result.append(
                RelatedNode(
                    node_id=graph_node.id,
                    label=graph_node.label,
                    score=max(
                        (hit.retrieval_score for hit in retrieved.results),
                        default=0.0,
                    ),
                )
            )
    return result


def ask_node(
    session: Session,
    settings: Settings,
    document: Document,
    node_id: str,
    question: str,
) -> AnswerResult:
    node = _find_node(session, settings, document, node_id)
    node_chunks = _node_chunks(session, document.id, node)
    extra_evidence = _chunk_to_evidence(node_chunks)
    return answer_question(
        session,
        settings,
        question,
        document_id=document.id,
        extra_evidence=extra_evidence,
    )
