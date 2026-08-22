"""Mind map view model.

The mind map is a view over the knowledge graph: a shallow, bounded tree
that loads fast. Every node carries invisible source metadata so the UI can
jump back to evidence without showing it in the label.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeSourceInfo(BaseModel):
    graph_node_id: str | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    is_inference: bool | None = None


class MindMapNode(BaseModel):
    id: str
    label: str
    node_type: str  # root | topic | concept
    depth: int
    children: list[MindMapNode] = Field(default_factory=list)
    source: NodeSourceInfo | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MindMap(BaseModel):
    document_id: str
    root: MindMapNode
    total_nodes: int
    max_depth: int


class MindMapPreferences(BaseModel):
    document_id: str
    layout: dict[str, Any] = Field(default_factory=dict)


class EvidenceChunk(BaseModel):
    chunk_id: str
    page_start: int
    page_end: int
    section_path: list[str] = Field(default_factory=list)
    text: str


class NodeEvidence(BaseModel):
    node_id: str
    label: str
    pages: list[int] = Field(default_factory=list)
    chunks: list[EvidenceChunk] = Field(default_factory=list)


class RelatedNode(BaseModel):
    node_id: str
    label: str
    relation: str | None = None
    score: float | None = None


class ExplainResult(BaseModel):
    node_id: str
    label: str
    explanation: str
    grounding: str = "inference"
    citations: list[dict[str, Any]] = Field(default_factory=list)
    related_concepts: list[RelatedNode] = Field(default_factory=list)


class ExpandResult(BaseModel):
    node_id: str
    added_nodes: list[dict[str, Any]] = Field(default_factory=list)
    added_edges: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    graph_version: int
    mindmap: MindMap | None = None
