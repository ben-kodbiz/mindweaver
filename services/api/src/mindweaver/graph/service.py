"""Knowledge graph service: extraction orchestration, persistence, and reads."""

from __future__ import annotations

import json
from typing import Any, cast

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


def _insert_node_item(session: Session, document_id: str, item: dict[str, Any]) -> None:
    record = GraphNodeRecord(
        document_id=document_id,
        node_id=item["node_id"],
        label=item["label"],
        node_type=item["node_type"],
        definition=item.get("definition", ""),
        note=item.get("note", ""),
        color=item.get("color"),
        tags=json.dumps(item.get("tags", [])),
        is_important=item.get("is_important", False),
        is_bookmarked=item.get("is_bookmarked", False),
        is_user_created=item.get("is_user_created", False),
        ai_accepted=item.get("ai_accepted", False),
    )
    session.add(record)
    session.flush()
    for chunk_id in item.get("source_chunks", []):
        session.add(
            NodeSourceRecord(node_id=record.id, chunk_id=chunk_id, page_start=0, page_end=0)
        )


def _insert_edge_item(session: Session, document_id: str, item: dict[str, Any]) -> None:
    session.add(
        GraphEdgeRecord(
            document_id=document_id,
            source_node_id=item["source_node_id"],
            target_node_id=item["target_node_id"],
            relation=item["relation"],
            note=item.get("note", ""),
            source_chunks=json.dumps(item.get("source_chunks", [])),
            is_inference=item.get("is_inference", False),
            is_user_created=item.get("is_user_created", False),
        )
    )


def replace_graph(
    session: Session,
    document: Document,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    warnings: list[str],
    *,
    operation: str = "extraction",
) -> int:
    """Replace the source-derived graph while preserving the personal layer.

    Personal nodes (``is_user_created``), personal connections, and any
    notes/colour/tags/flags the user attached to source nodes survive
    regeneration. Afterwards the edit history is re-baselined.
    """
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

    # Capture the personal layer as plain dicts before deleting anything:
    # personal nodes survive wholesale, and user annotations (notes, colour,
    # tags, flags) on source-derived nodes are re-attached after regeneration.
    user_nodes: list[dict[str, Any]] = []
    personal_node_ids: set[str] = set()
    user_meta: dict[str, dict[str, Any]] = {}
    for record in session.scalars(
        select(GraphNodeRecord).where(GraphNodeRecord.document_id == document.id)
    ).all():
        meta: dict[str, Any] = {
            "note": record.note,
            "color": record.color,
            "tags": _json_loads(record.tags),
            "is_important": record.is_important,
            "is_bookmarked": record.is_bookmarked,
        }
        item = {
            "node_id": record.node_id,
            "label": record.label,
            "node_type": record.node_type,
            "definition": record.definition,
            **meta,
            "source_chunks": [
                row[0].chunk_id
                for row in session.execute(
                    select(NodeSourceRecord).where(NodeSourceRecord.node_id == record.id)
                ).all()
            ],
        }
        user_meta[record.node_id] = meta
        if record.is_user_created:
            user_nodes.append(item)
            personal_node_ids.add(record.node_id)
        else:
            # keep the stored source evidence for annotation restore
            user_meta[record.node_id]["_source_chunks"] = item["source_chunks"]

    user_edges: list[dict[str, Any]] = [
        {
            "source_node_id": record.source_node_id,
            "target_node_id": record.target_node_id,
            "relation": record.relation,
            "note": record.note,
            "source_chunks": _json_loads(record.source_chunks),
            "is_inference": record.is_inference,
        }
        for record in session.scalars(
            select(GraphEdgeRecord).where(
                GraphEdgeRecord.document_id == document.id,
                GraphEdgeRecord.is_user_created.is_(True),
            )
        ).all()
    ]
    user_edge_keys = {
        (item["source_node_id"], item["target_node_id"], item["relation"]) for item in user_edges
    }

    # Clean slate.
    session.execute(delete(GraphNodeRecord).where(GraphNodeRecord.document_id == document.id))
    session.execute(delete(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document.id))

    inserted_ids: set[str] = set()

    # 1) Personal nodes first: their stable ids win over regenerated ones.
    for item in user_nodes:
        _insert_node_item(session, document.id, item)
        inserted_ids.add(item["node_id"])

    # 2) Extracted nodes; re-attach user annotations on id collision.
    for node in nodes:
        item = {
            "node_id": node.id,
            "label": node.label,
            "node_type": node.type.value,
            "definition": node.definition,
            "source_chunks": list(node.source_chunks),
        }
        previous_meta = user_meta.get(node.id)
        if previous_meta is not None:
            item.update(previous_meta)
            saved_chunks = previous_meta.get("_source_chunks", [])
            item["source_chunks"] = sorted(set(item["source_chunks"]) | set(saved_chunks))
        _insert_node_item(session, document.id, item)
        inserted_ids.add(node.id)

    # 3) Extracted edges, skipping triples already covered by connections.
    for edge in edges:
        if (edge.source, edge.target, edge.relation.value) in user_edge_keys:
            continue
        _insert_edge_item(
            session,
            document.id,
            {
                "source_node_id": edge.source,
                "target_node_id": edge.target,
                "relation": edge.relation.value,
                "note": edge.note,
                "source_chunks": edge.source_chunks,
                "is_inference": edge.is_inference,
            },
        )

    # 4) Personal connections back.
    for item in user_edges:
        _insert_edge_item(session, document.id, item)

    # 5) Drop edges whose endpoints no longer exist.
    session.execute(
        delete(GraphEdgeRecord).where(
            GraphEdgeRecord.document_id == document.id,
            GraphEdgeRecord.source_node_id.not_in(inserted_ids)
            | GraphEdgeRecord.target_node_id.not_in(inserted_ids),
        )
    )

    session.flush()

    from mindweaver.graph.history import seed_baseline

    seed_baseline(session, document)
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
                is_user_created=edge.is_user_created,
            )
        )
    session.flush()

    from mindweaver.graph.history import seed_baseline

    seed_baseline(session, document)
    return next_version


def get_graph(
    session: Session,
    document_id: str,
    *,
    node_types: list[str] | None = None,
    relations: list[str] | None = None,
    focus_node_id: str | None = None,
    limit: int | None = None,
) -> GraphRead | None:
    """Load the document graph, optionally filtered and capped.

    ``node_types``/``relations`` filter what is returned; ``focus_node_id``
    keeps only the focus node's neighbourhood (1 hop); ``limit`` caps the
    number of rendered nodes (highest degree first) so huge graphs stay usable.
    """
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
        if node_types is not None and record.node_type not in node_types:
            continue
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
                note=record.note,
                color=record.color,
                tags=_json_loads(record.tags),
                is_important=record.is_important,
                is_bookmarked=record.is_bookmarked,
                is_user_created=record.is_user_created,
                ai_accepted=getattr(record, "ai_accepted", False),
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
            is_user_created=record.is_user_created,
        )
        for record in session.scalars(
            select(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document_id)
        ).all()
        if relations is None or record.relation in relations
    ]

    if focus_node_id is not None:
        neighbours = {edge.source for edge in edges if edge.target == focus_node_id} | {
            edge.target for edge in edges if edge.source == focus_node_id
        }
        keep = neighbours | {focus_node_id}
        nodes = [node for node in nodes if node.id in keep]
        edges = [edge for edge in edges if edge.source in keep and edge.target in keep]

    if limit is not None and len(nodes) > limit:
        degree: dict[str, int] = {}
        for edge in edges:
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1
        kept_ids = {
            node.id
            for node in sorted(nodes, key=lambda n: degree.get(n.id, 0), reverse=True)[:limit]
        }
        nodes = [node for node in nodes if node.id in kept_ids]
        edges = [edge for edge in edges if edge.source in kept_ids and edge.target in kept_ids]

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
