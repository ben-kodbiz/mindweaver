"""Chat answer types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    chapter: str | None = None
    section: str | None = None


Grounding = Literal["supported_by_source", "inference", "not_found"]


class AnswerResult(BaseModel):
    question: str
    answer: str
    grounding: Grounding = "not_found"
    citations: list[Citation] = Field(default_factory=list)
