"""Summaries and learning outputs.

Every generated output retains references to its sources: concept ids ->
source chunks -> pages. The LLM drafts content; the service layer attaches
provenance from the graph and chunk store so nothing is uncited.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from mindweaver.chunking.service import list_chunks
from mindweaver.config import Settings
from mindweaver.graph.service import get_graph
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.models import ChunkRecord, Document

LearningKind = Literal["summary", "key_concepts", "qa", "flashcards", "quiz", "study_guide"]

LEARNING_KINDS = (
    "summary",
    "key_concepts",
    "qa",
    "flashcards",
    "quiz",
    "study_guide",
)


class LearningError(Exception):
    pass


def _scope_chunks(
    chunks: list[ChunkRecord], scope_type: str, target: str | None
) -> list[ChunkRecord]:
    if scope_type == "document" or not target:
        return chunks
    needle = re.escape(target.strip().lower())
    selected = [
        chunk
        for chunk in chunks
        if re.search(needle, chunk.text.lower())
        or re.search(needle, (chunk.section_path or "").lower())
    ]
    return selected or chunks


def _key_concept_labels(session: Session, document_id: str) -> list[tuple[str, str]]:
    graph = get_graph(session, document_id)
    if graph is None:
        return []
    ranked = sorted(
        graph.nodes,
        key=lambda n: sum(1 for e in graph.edges if e.source == n.id or e.target == n.id),
        reverse=True,
    )
    return [(node.id, node.label) for node in ranked[:8]]


def _attach_provenance(
    items: list[dict[str, Any]],
    concept_ids: dict[str, str],
    chunks: list[ChunkRecord],
) -> list[dict[str, Any]]:
    for item in items:
        text = json.dumps(item, ensure_ascii=False).lower()
        labels = [label.lower() for label in concept_ids]
        found_concepts = [concept_ids[label] for label in labels if label and label in text]
        pages = sorted(
            {page for chunk in chunks for page in range(chunk.page_start, chunk.page_end + 1)}
        )
        relevant_pages: list[int] = []
        for chunk in chunks:
            snippet = chunk.text.lower()
            if any(label in snippet for label in labels):
                relevant_pages.extend(range(chunk.page_start, chunk.page_end + 1))
        item["concept_ids"] = sorted(set(found_concepts))
        item["chunk_ids"] = [chunk.chunk_id for chunk in chunks][:6]
        item["pages"] = sorted(set(relevant_pages)) or pages[:5]
    return items


SYSTEM_PROMPT = (
    "You generate study material from document evidence. Respond with JSON only: "
    '{"items": [<kind-specific objects>]}. Each item must be grounded in the '
    "evidence; do not invent facts. Keep item texts concise."
)


def _fallback_items(
    kind: LearningKind,
    chunks: list[ChunkRecord],
    concepts: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Deterministic extractive outputs used when no LLM output is available."""
    top_chunks = chunks[:5]
    sentences: list[str] = []
    for chunk in top_chunks:
        for sentence in re.split(r"(?<=[.!?])\s+", chunk.text):
            clean = sentence.strip()
            if len(clean) > 30:
                sentences.append(clean)
    if kind == "summary":
        return [{"text": text} for text in sentences[:4]]
    if kind == "key_concepts":
        return [
            {"term": label, "text": "Key concept covered by the document."}
            for _, label in concepts[:6]
        ]
    if kind == "qa":
        return [
            {"question": f"What does the document say about {label}?", "answer": text}
            for (_, label), text in zip(concepts[:4], sentences, strict=False)
        ] or [{"question": "Main topic?", "answer": sentences[0] if sentences else ""}]
    if kind == "flashcards":
        return [
            {"front": f"Define: {label}", "back": text}
            for (_, label), text in zip(concepts[:4], sentences, strict=False)
        ] or [{"front": "Main idea", "back": sentences[0] if sentences else ""}]
    if kind == "quiz":
        items = [
            {
                "question": f"Which concept does this describe: {text[:80]}?",
                "options": [c[1] for c in concepts[:3]] or ["Memory"],
                "answer_index": 0,
            }
            for text in sentences[:3]
        ]
        return items or [{"question": "Placeholder", "options": ["A"], "answer_index": 0}]
    # study guide
    return [
        {
            "section": label,
            "points": sentences[i * 2 : i * 2 + 2],
        }
        for i, (_, label) in enumerate(concepts[:4])
    ] or [{"section": "Overview", "points": sentences[:2]}]


def generate_learning_output(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    kind: LearningKind,
    scope_type: str = "document",
    target: str | None = None,
) -> dict[str, Any]:
    if kind not in LEARNING_KINDS:
        raise LearningError(f"unknown learning kind: {kind}")
    all_chunks = list_chunks(session, document.id)
    chunks = _scope_chunks(all_chunks, scope_type, target)
    concepts_list = _key_concept_labels(session, document.id)
    concept_ids = {label.lower(): cid for cid, label in concepts_list}

    items: list[dict[str, Any]]
    generated_by = "llm"
    try:
        provider = get_llm_provider(settings)
        evidence = "\n\n".join(
            f"[{index}] (pages={chunk.page_start}-{chunk.page_end})\n{chunk.text}"
            for index, chunk in enumerate(chunks[:8], start=1)
        )
        concept_names = ", ".join(label for _, label in concepts_list)
        raw = provider.complete(
            [
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=(
                        f"Generate {kind.replace('_', ' ')} for the document "
                        f"'{document.title}'. Key concepts: {concept_names}.\n\n"
                        f"Evidence:\n\n{evidence}"
                    ),
                ),
            ],
            temperature=settings.llm.temperature,
            max_tokens=settings.chat.max_tokens,
        )
        payload = extract_json(raw)
        candidate_items = payload.get("items") if payload else None
        if not isinstance(candidate_items, list) or not candidate_items:
            raise LearningError("empty learning output")
        items = [item for item in candidate_items if isinstance(item, dict)]
    except Exception:
        generated_by = "extractive"
        items = _fallback_items(kind, chunks, concepts_list)

    items = _attach_provenance(items, concept_ids, chunks)

    return {
        "document_id": document.id,
        "kind": kind,
        "scope": {"type": scope_type, "target": target},
        "generated_by": generated_by,
        "items": items,
    }
