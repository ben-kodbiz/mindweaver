"""Project-owned canonical document format.

Every document processor (Docling, native pypdf, future OCR pipelines) must
output this format. Downstream consumers (chunking, search, graph, mind map)
must never depend on a specific processor's internal representation.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class BlockType(enum.StrEnum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    FORMULA = "formula"
    OTHER = "other"


class BoundingBox(BaseModel):
    page_number: int
    left: float
    top: float
    right: float
    bottom: float


class Page(BaseModel):
    page_number: int
    width: float | None = None
    height: float | None = None
    extraction_method: str = "native"
    confidence: float | None = None
    low_confidence: bool = False


class Section(BaseModel):
    id: str
    title: str
    level: int
    page_number: int
    section_path: list[str] = Field(default_factory=list)
    children: list[Section] = Field(default_factory=list)


class ContentBlock(BaseModel):
    block_id: str
    document_id: str
    page_number: int
    block_type: BlockType
    text: str
    section_path: list[str] = Field(default_factory=list)
    bbox: BoundingBox | None = None
    source_confidence: float | None = None
    table_rows: list[list[str]] | None = None
    figure_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalDocument(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    source_filename: str
    processor: str
    pages: list[Page] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
