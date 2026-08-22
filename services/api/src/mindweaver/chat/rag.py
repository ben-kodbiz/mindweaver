"""RAG answer generation: evidence retrieval + LLM + citation mapping.

The LLM must distinguish SUPPORTED BY SOURCE / INFERENCE / NOT FOUND and
answer "I don't know from the provided sources." when the evidence does not
contain the answer.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from mindweaver.chat.types import AnswerResult, Citation, Grounding
from mindweaver.config import Settings
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.jsonutil import extract_json as _extract_json
from mindweaver.llm.registry import get_llm_provider
from mindweaver.search.base import SearchHit
from mindweaver.search.service import search

logger = logging.getLogger(__name__)

NOT_FOUND_ANSWER = "I don't know from the provided sources."

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful research assistant. Answer the user's question using ONLY the "
    "provided evidence. Each evidence item is numbered [1], [2], ... and carries its "
    "source (document, pages, section).\n"
    "Respond with JSON only, using exactly this schema:\n"
    '{"answer": "...", "grounding": "supported_by_source|inference|not_found", '
    '"citations": [<evidence numbers>]}\n'
    '- grounding is "supported_by_source" when the answer is directly stated in the '
    'cited evidence; "inference" when you reason from it; "not_found" when the '
    "evidence does not contain the answer.\n"
    '- When grounding is "not_found", the answer must be exactly '
    '"I don\'t know from the provided sources." and citations must be [] (empty).\n'
    "Cite evidence by number. Never invent facts, sources, pages, or citations.\n"
    "Output the JSON object immediately as your entire reply — no planning, "
    "reasoning, or commentary before or after it."
)


def _evidence_block(index: int, hit: SearchHit) -> str:
    source = f"document={hit.document_id[:8]}"
    if hit.section_path:
        source += f", section={'/'.join(hit.section_path)}"
    source += f", pages={hit.page_start}-{hit.page_end}"
    return f"[{index}] ({source})\n{hit.text}"


def build_messages(question: str, evidence: list[SearchHit]) -> list[LLMMessage]:
    blocks = [_evidence_block(index, hit) for index, hit in enumerate(evidence, start=1)]
    if blocks:
        evidence_text = "\n\n".join(blocks)
        user_content = f"Evidence:\n\n{evidence_text}\n\nQuestion: {question}"
    else:
        user_content = f"There is no relevant evidence for this question.\n\nQuestion: {question}"
    return [
        LLMMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]


def _grounding(value: Any) -> Grounding:
    if value in ("supported_by_source", "inference", "not_found"):
        return cast(Grounding, value)
    return "inference"


def _map_citations(payload: dict[str, Any], evidence: list[SearchHit]) -> list[Citation]:
    citations: list[Citation] = []
    raw = payload.get("citations") or []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            try:
                index = int(item) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(evidence):
                hit = evidence[index]
                citations.append(
                    Citation(
                        chunk_id=hit.chunk_id,
                        document_id=hit.document_id,
                        page_start=hit.page_start,
                        page_end=hit.page_end,
                        chapter=hit.chapter,
                        section=hit.section,
                    )
                )
    return citations


def answer_question(
    session: Session,
    settings: Settings,
    question: str,
    *,
    document_id: str | None = None,
    extra_evidence: list[SearchHit] | None = None,
) -> AnswerResult:
    retrieved = search(
        session,
        settings,
        question,
        document_id=document_id,
        limit=settings.chat.evidence_limit,
    ).results

    evidence = list(extra_evidence or []) + [
        hit for hit in retrieved if hit.chunk_id not in {e.chunk_id for e in extra_evidence or []}
    ]

    if not evidence:
        return AnswerResult(
            question=question,
            answer=NOT_FOUND_ANSWER,
            grounding="not_found",
            citations=[],
        )

    provider = get_llm_provider(settings)
    messages = build_messages(question, evidence)
    raw = provider.complete(
        messages,
        temperature=settings.llm.temperature,
        max_tokens=settings.chat.max_tokens,
    )

    payload = _extract_json(raw)
    if payload is None:
        logger.warning("LLM returned non-JSON answer; marking as inference")
        return AnswerResult(
            question=question,
            answer=raw.strip() or NOT_FOUND_ANSWER,
            grounding="inference",
            citations=[],
        )

    grounding = _grounding(payload.get("grounding"))
    answer = str(payload.get("answer") or "").strip()
    if grounding == "not_found":
        answer = NOT_FOUND_ANSWER
    citations = _map_citations(payload, evidence)
    return AnswerResult(
        question=question,
        answer=answer or NOT_FOUND_ANSWER,
        grounding=grounding,
        citations=citations,
    )
