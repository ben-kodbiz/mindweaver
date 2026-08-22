"""Knowledge graph types.

The mind map is a view; this graph is the underlying intelligence. Every
node/edge keeps its source chunk references so relationships stay traceable
to evidence (or are explicitly marked as inference).
"""

from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, Field


class GraphNodeType(enum.StrEnum):
    CONCEPT = "concept"
    CLAIM = "claim"
    EVENT = "event"
    PERSON = "person"
    TOPIC = "topic"


class GraphEdgeType(enum.StrEnum):
    EXPLAINS = "explains"
    CAUSES = "causes"
    AFFECTS = "affects"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    EXAMPLE_OF = "example_of"


_ALLOWED_EDGE_NAMES = {member.name for member in GraphEdgeType}
_ALLOWED_EDGE_VALUES = {member.value for member in GraphEdgeType}


def normalize_edge_type(value: Any) -> GraphEdgeType | None:
    if not isinstance(value, str):
        return None
    name = value.strip().upper().replace(" ", "_")
    if name in _ALLOWED_EDGE_NAMES:
        return GraphEdgeType[name]
    if value.strip().lower() in _ALLOWED_EDGE_VALUES:
        return GraphEdgeType(value.strip().lower())
    return None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int = 48) -> str:
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug[:max_length].rstrip("-") or "unknown"


class GraphNode(BaseModel):
    id: str
    label: str
    type: GraphNodeType
    definition: str = ""
    source_chunks: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    note: str = ""
    color: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_important: bool = False
    is_bookmarked: bool = False
    is_user_created: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: GraphEdgeType
    note: str = ""
    source_chunks: list[str] = Field(default_factory=list)
    is_inference: bool = False
    is_user_created: bool = False


class GraphRead(BaseModel):
    document_id: str
    version: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
