"""Knowledge graph extraction from chunked content.

Concepts and relationships are extracted per section by the configured LLM
(behind the provider interface); the engine validates, deduplicates, and
attributes every node/edge to its source chunks so the graph stays traceable.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from mindweaver.chunking.service import list_chunks
from mindweaver.config import Settings
from mindweaver.graph.types import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    normalize_edge_type,
    slugify,
)
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.models import ChunkRecord, Document

_NODE_TYPES = {member.value for member in GraphNodeType}


class GraphExtractionError(Exception):
    pass


def _chunk_text(chunks: list[ChunkRecord]) -> str:
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        section = " / ".join(_json_loads(chunk.section_path)) or "(root)"
        blocks.append(
            f"[{index}] (pages={chunk.page_start}-{chunk.page_end}, "
            f"section={section})\n{chunk.text}"
        )
    return "\n\n".join(blocks)


def _json_loads(value: str) -> list[str]:
    import json
    from typing import cast as _cast

    try:
        return _cast(list[str], json.loads(value))
    except Exception:
        return []


logger = logging.getLogger("mindweaver.graph.extractor")

SYSTEM_PROMPT = (
    "You extract a knowledge graph from a document. Node types: concept, claim, "
    "event, person, topic. Allowed relations: EXPLAINS, CAUSES, AFFECTS, SUPPORTS, "
    "CONTRADICTS, PART_OF, RELATED_TO, PRECEDES, FOLLOWS, EXAMPLE_OF.\n"
    "Respond with JSON only, using exactly this schema:\n"
    '{"concepts": [{"label": "...", "type": "concept", "definition": "..."}], '
    '"relations": [{"source": "<label>", "target": "<label>", "relation": "AFFECTS", '
    '"note": "..."}]}\n'
    "Only extract concepts that actually appear in the evidence. Use labels exactly "
    "as they appear in the text. Do not invent sources."
)


def build_messages(chunk_text: str) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=(
                "Extract concepts and relationships from the following document content.\n\n"
                f"{chunk_text}"
            ),
        ),
    ]


def _label_to_node_key(label: str, node_type: GraphNodeType) -> tuple[str, str]:
    return (node_type.value, slugify(label))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _stem(word: str) -> str:
    for suffix, replacement in (("ies", "y"), ("es", ""), ("ed", ""), ("ing", ""), ("s", "")):
        if word.endswith(suffix) and len(word) > 4:
            return word[: -len(suffix)] + replacement
    return word


def _word_match(label_word: str, text_word: str) -> bool:
    if label_word == text_word:
        return True
    if len(label_word) >= 4 and (label_word in text_word or text_word.startswith(label_word)):
        return True
    return len(text_word) >= 4 and label_word.startswith(text_word)


def _mentioned(label: str, text: str) -> bool:
    label_words = [_stem(word) for word in _words(label)]
    text_words = [_stem(word) for word in _words(text)]
    if not label_words:
        return False
    return all(
        any(_word_match(label_word, text_word) for text_word in text_words)
        for label_word in label_words
    )


def _chunks_mention(label: str, chunks: list[ChunkRecord]) -> list[Any]:
    return [chunk for chunk in chunks if _mentioned(label, chunk.text)]


def normalize_graph(
    payload: dict[str, Any],
    document_id: str,
    chunks: list[ChunkRecord],
    known_labels: dict[str, list[str]] | None = None,
) -> tuple[list[GraphNode], list[GraphEdge], list[str]]:
    warnings: list[str] = []
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_by_key: dict[tuple[str, str], GraphNode] = {}
    label_index: dict[str, list[str]] = defaultdict(list, known_labels or {})

    for item in payload.get("concepts") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            warnings.append("skipped concept without a label")
            continue
        raw_type = str(item.get("type") or "concept").strip().lower()
        if raw_type not in _NODE_TYPES:
            warnings.append(f"unknown node type {raw_type!r}; defaulting to concept")
            node_type = GraphNodeType.CONCEPT
        else:
            node_type = GraphNodeType(raw_type)

        key = _label_to_node_key(label, node_type)
        definition = str(item.get("definition") or "").strip()
        sources = [chunk.chunk_id for chunk in _chunks_mention(label, chunks)]
        page_numbers = sorted(
            {page for chunk in chunks for page in range(chunk.page_start, chunk.page_end + 1)}
        )

        existing = node_by_key.get(key)
        if existing is not None:
            warnings.append(f"duplicate concept '{label}' merged")
            existing.source_chunks = sorted(set(existing.source_chunks) | set(sources))
            if not existing.definition:
                existing.definition = definition
            continue

        node = GraphNode(
            id=f"{node_type.value}:{slugify(label)}",
            label=label,
            type=node_type,
            definition=definition,
            source_chunks=sources,
            page_numbers=page_numbers,
        )
        nodes.append(node)
        node_by_key[key] = node
        label_index[label.lower()].append(node.id)

    for item in payload.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source_label = str(item.get("source") or "").strip()
        target_label = str(item.get("target") or "").strip()
        relation = normalize_edge_type(item.get("relation"))
        if relation is None:
            warnings.append(f"invalid relation {item.get('relation')!r} skipped")
            continue
        source_ids = label_index.get(source_label.lower())
        target_ids = label_index.get(target_label.lower())
        if not source_ids or not target_ids:
            warnings.append(
                f"relation {source_label} -{relation.value}-> {target_label} "
                "references unknown nodes; skipped"
            )
            continue
        if len(source_ids) > 1 or len(target_ids) > 1:
            warnings.append(
                f"ambiguous label in relation {source_label} -{relation.value}-> "
                f"{target_label}; using the first match"
            )
        edge_sources = [
            chunk.chunk_id
            for chunk in chunks
            if _mentioned(source_label, chunk.text) and _mentioned(target_label, chunk.text)
        ]
        edges.append(
            GraphEdge(
                source=source_ids[0],
                target=target_ids[0],
                relation=relation,
                note=str(item.get("note") or "").strip(),
                source_chunks=edge_sources,
                is_inference=not edge_sources,
            )
        )

    edges = _dedupe_edges(edges, warnings)
    return nodes, edges, warnings


def _dedupe_edges(edges: list[GraphEdge], warnings: list[str]) -> list[GraphEdge]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[GraphEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.relation.value)
        if key in seen:
            warnings.append(f"duplicate relation {key} dropped")
            continue
        seen.add(key)
        unique.append(edge)
    return unique


def extract_graph(
    session: Session, settings: Settings, document: Document
) -> tuple[list[GraphNode], list[GraphEdge], list[str]]:
    chunks = list_chunks(session, document.id)[: settings.graph.max_chunks]
    if not chunks:
        return [], [], []

    provider = get_llm_provider(settings)
    messages = build_messages(_chunk_text(chunks))
    raw = provider.complete(
        messages,
        temperature=settings.llm.temperature,
        max_tokens=settings.graph.max_tokens,
    )

    payload = extract_json(raw)
    if payload is None:
        logger.error(
            "graph.extract invalid JSON raw_len=%d head=%r tail=%r",
            len(raw),
            raw[:500],
            raw[-500:],
        )
        raise GraphExtractionError("LLM returned invalid JSON for graph extraction")

    nodes, edges, warnings = normalize_graph(payload, document.id, chunks)
    return nodes[: settings.graph.max_nodes], edges, warnings
