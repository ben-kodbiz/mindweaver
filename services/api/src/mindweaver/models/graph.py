"""Knowledge graph persistence (nodes, edges, node sources, versions)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mindweaver.models.base import Base
from mindweaver.models.document import new_id, utcnow


class GraphNodeRecord(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("document_id", "node_id", name="uq_graph_nodes_node"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(256))
    label: Mapped[str] = mapped_column(String(512))
    node_type: Mapped[str] = mapped_column(String(32))
    definition: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    is_important: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user_created: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class NodeSourceRecord(Base):
    __tablename__ = "node_sources"
    __table_args__ = (UniqueConstraint("node_id", "chunk_id", name="uq_node_sources_chunk"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(128))
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraphEdgeRecord(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "source_node_id", "target_node_id", "relation", name="uq_graph_edges_rel"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_node_id: Mapped[str] = mapped_column(String(256))
    target_node_id: Mapped[str] = mapped_column(String(256))
    relation: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    source_chunks: Mapped[str] = mapped_column(Text, default="[]")
    is_inference: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user_created: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraphVersionRecord(Base):
    __tablename__ = "graph_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_graph_versions_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraphHistoryEntry(Base):
    __tablename__ = "graph_history"
    __table_args__ = (UniqueConstraint("document_id", "position", name="uq_graph_history_pos"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(128), default="")
    snapshot: Mapped[str] = mapped_column(Text)


class GraphHistoryState(Base):
    __tablename__ = "graph_history_state"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
