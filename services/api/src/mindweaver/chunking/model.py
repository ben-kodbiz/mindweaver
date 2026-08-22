"""Chunk model.

Chunks are the retrieval unit produced by structural chunking. Every chunk
preserves enough provenance to reconstruct its place in the book:
``Book -> Chapter -> Section -> Page -> Source text``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Chunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    section_path: list[str] = Field(default_factory=list)
    text: str
    token_count: int
    parent_chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
