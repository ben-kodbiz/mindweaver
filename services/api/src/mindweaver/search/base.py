"""Search result types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    chapter: str | None = None
    section: str | None = None
    section_path: list[str] = Field(default_factory=list)
    text: str
    keyword_score: float | None = None
    vector_score: float | None = None
    retrieval_score: float
    rerank_score: float | None = None
    rank: int = 0
    source_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]
