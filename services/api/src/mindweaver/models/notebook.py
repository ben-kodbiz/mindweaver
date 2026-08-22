"""Notebooks: workspaces grouping multiple documents for cross-document work."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mindweaver.models.base import Base
from mindweaver.models.document import new_id, utcnow


class Notebook(Base):
    __tablename__ = "notebooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class NotebookDocument(Base):
    __tablename__ = "notebook_documents"
    __table_args__ = (UniqueConstraint("notebook_id", "document_id", name="uq_notebook_documents"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    notebook_id: Mapped[str] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
