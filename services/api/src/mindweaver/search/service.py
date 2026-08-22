"""Hybrid search service: keyword + vector -> merge -> rerank."""

from __future__ import annotations

import json
import logging
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.models import ChunkRecord
from mindweaver.search.base import SearchHit, SearchResponse
from mindweaver.search.embeddings.registry import get_embedding_provider
from mindweaver.search.fts import keyword_search
from mindweaver.search.rerank import get_reranker
from mindweaver.search.vector import vector_search

logger = logging.getLogger(__name__)


def _bm25_to_similarity(score: float) -> float:
    """Map a negative bm25 score to a 0..1 similarity (larger is better)."""
    return 1.0 / (1.0 + abs(score))


def search(
    session: Session,
    settings: Settings,
    query: str,
    *,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    with_labels: bool = False,
    limit: int | None = None,
) -> SearchResponse:
    cfg = settings.search
    limit = limit or cfg.default_limit

    keyword_scores = {
        hit["chunk_id"]: _bm25_to_similarity(hit["score"])
        for hit in keyword_search(
            session,
            query,
            document_id=document_id,
            document_ids=document_ids,
            limit=cfg.keyword_limit,
        )
    }

    vector_scores: dict[str, float] = {}
    provider = get_embedding_provider(settings)
    if provider is not None:
        query_vector = provider.embed([query])[0]
        vector_scores = {
            str(hit["chunk_id"]): float(hit["score"])
            for hit in vector_search(
                session,
                query_vector,
                provider.model_name,
                document_id=document_id,
                document_ids=document_ids,
                limit=cfg.vector_limit,
            )
        }

    candidate_ids = list(keyword_scores.keys() | vector_scores.keys())
    records = session.scalars(
        select(ChunkRecord).where(ChunkRecord.chunk_id.in_(candidate_ids))
    ).all()
    record_by_id = {record.chunk_id: record for record in records}

    hits: list[SearchHit] = []
    for chunk_id in candidate_ids:
        record = record_by_id.get(chunk_id)
        if record is None:
            continue
        keyword_score = keyword_scores.get(chunk_id)
        vector_score = vector_scores.get(chunk_id)

        weighted = 0.0
        denominator = 0.0
        if keyword_score is not None:
            weighted += cfg.fts_weight * keyword_score
            denominator += cfg.fts_weight
        if vector_score is not None:
            weighted += cfg.vector_weight * vector_score
            denominator += cfg.vector_weight
        retrieval_score = weighted / denominator if denominator else 0.0

        hits.append(
            SearchHit(
                chunk_id=chunk_id,
                document_id=record.document_id,
                page_start=record.page_start,
                page_end=record.page_end,
                chapter=record.chapter,
                section=record.section,
                section_path=_parse_section_path(record.section_path),
                text=record.text,
                keyword_score=keyword_score,
                vector_score=vector_score,
                retrieval_score=retrieval_score,
            )
        )

    reranker = get_reranker(settings)
    if reranker is not None:
        hits = reranker.rerank(query, hits)
    else:
        hits.sort(key=lambda hit: hit.retrieval_score, reverse=True)

    hits = [hit for hit in hits if hit.retrieval_score >= cfg.min_score]
    for rank, hit in enumerate(hits[:limit], start=1):
        hit.rank = rank

    results = hits[:limit]
    if with_labels and results:
        _attach_source_labels(session, results)

    return SearchResponse(query=query, total=len(results), results=results)


def _attach_source_labels(session: Session, results: list[SearchHit]) -> None:
    from mindweaver.models import Document

    ids = {hit.document_id for hit in results}
    rows: list[tuple[str, str]] = [
        (row[0], row[1])
        for row in session.execute(
            select(Document.id, Document.title).where(Document.id.in_(ids))
        ).all()
    ]
    titles: dict[str, str] = {doc_id: title for doc_id, title in rows}
    for hit in results:
        hit.source_label = titles.get(hit.document_id)


def _parse_section_path(value: str) -> list[str]:
    try:
        return cast(list[str], json.loads(value))
    except Exception:
        return []
