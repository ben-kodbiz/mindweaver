"""Knowledge graph service: extraction orchestration, persistence, and reads."""

from __future__ import annotations

import json
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.graph.extractor import extract_graph
from mindweaver.graph.types import (
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    GraphRead,
)
from mindweaver.models import (
    Document,
    GraphEdgeRecord,
    GraphNodeRecord,
    GraphVersionRecord,
    JobStatus,
    JobType,
    NodeSourceRecord,
    ProcessingJob,
)
from mindweaver.models.document import utcnow


def run_graph_extraction(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    operation: str = "extraction",
) -> None:
    """Extract and persist the document graph. Never raises; failures are
    recorded on a failed job so the document itself stays usable."""
    job = ProcessingJob(
        document_id=document.id,
        job_type=JobType.GRAPH_EXTRACTION,
        status=JobStatus.RUNNING,
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()
    try:
        nodes, edges, warnings = extract_graph(session, settings, document)
        replace_graph(session, document, nodes, edges, warnings, operation=operation)
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.completed_at = utcnow()
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = utcnow()


def replace_graph(
    session: Session,
    document: Document,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    warnings: list[str],
    *,
    operation: str = "extraction",
) -> int:
    next_version = (
        session.scalar(
            select(func.max(GraphVersionRecord.version)).where(
                GraphVersionRecord.document_id == document.id
            )
        )
        or 0
    ) + 1

    session.add(
        GraphVersionRecord(
            document_id=document.id,
            version=next_version,
            operation=operation,
            notes=json.dumps(warnings),
        )
    )

    session.execute(delete(GraphNodeRecord).where(GraphNodeRecord.document_id == document.id))
    session.execute(delete(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document.id))

    for node in nodes:
        record = GraphNodeRecord(
            document_id=document.id,
            node_id=node.id,
            label=node.label,
            node_type=node.type.value,
            definition=node.definition,
            is_user_created=node.is_user_created,
        )
        session.add(record)
        session.flush()
        for chunk_id in node.source_chunks:
            session.add(
                NodeSourceRecord(
                    node_id=record.id,
                    chunk_id=chunk_id,
                    page_start=0,
                    page_end=0,
                )
            )

    for edge in edges:
        session.add(
            GraphEdgeRecord(
                document_id=document.id,
                source_node_id=edge.source,
                target_node_id=edge.target,
                relation=edge.relation.value,
                note=edge.note,
                source_chunks=json.dumps(edge.source_chunks),
                is_inference=edge.is_inference,
            )
        )
    session.flush()
    return next_version


def append_graph(
    session: Session,
    document: Document,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    warnings: list[str],
    *,
    operation: str = "expand",
) -> int:
    """Incrementally add nodes/edges to an existing graph (for expansion)."""
    next_version = (
        session.scalar(
            select(func.max(GraphVersionRecord.version)).where(
                GraphVersionRecord.document_id == document.id
            )
        )
        or 0
    ) + 1

    session.add(
        GraphVersionRecord(
            document_id=document.id,
            version=next_version,
            operation=operation,
            notes=json.dumps(warnings),
        )
    )

    for node in nodes:
        record = GraphNodeRecord(
            document_id=document.id,
            node_id=node.id,
            label=node.label,
            node_type=node.type.value,
            definition=node.definition,
            is_user_created=node.is_user_created,
        )
        session.add(record)
        session.flush()
        for chunk_id in node.source_chunks:
            session.add(
                NodeSourceRecord(
                    node_id=record.id,
                    chunk_id=chunk_id,
                    page_start=0,
                    page_end=0,
                )
            )

    for edge in edges:
        session.add(
            GraphEdgeRecord(
                document_id=document.id,
                source_node_id=edge.source,
                target_node_id=edge.target,
                relation=edge.relation.value,
                note=edge.note,
                source_chunks=json.dumps(edge.source_chunks),
                is_inference=edge.is_inference,
            )
        )
    session.flush()
    return next_version


def get_graph(session: Session, document_id: str) -> GraphRead | None:
    version = session.scalar(
        select(func.max(GraphVersionRecord.version)).where(
            GraphVersionRecord.document_id == document_id
        )
    )
    if version is None:
        return None

    nodes: list[GraphNode] = []
    for record in session.scalars(
        select(GraphNodeRecord).where(GraphNodeRecord.document_id == document_id)
    ).all():
        source_rows = session.execute(
            select(NodeSourceRecord).where(NodeSourceRecord.node_id == record.id)
        ).all()
        nodes.append(
            GraphNode(
                id=record.node_id,
                label=record.label,
                type=GraphNodeType(record.node_type),
                definition=record.definition,
                source_chunks=[row[0].chunk_id for row in source_rows],
                is_user_created=record.is_user_created,
            )
        )

    edges = [
        GraphEdge(
            source=record.source_node_id,
            target=record.target_node_id,
            relation=GraphEdgeType(record.relation),
            note=record.note,
            source_chunks=_json_loads(record.source_chunks),
            is_inference=record.is_inference,
        )
        for record in session.scalars(
            select(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document_id)
        ).all()
    ]

    return GraphRead(
        document_id=document_id,
        version=int(version),
        nodes=nodes,
        edges=edges,
    )


def _json_loads(value: str) -> list[str]:
    try:
        return cast(list[str], json.loads(value))
    except Exception:
        return []
