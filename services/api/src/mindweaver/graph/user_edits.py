"""User graph edits: personal nodes, notes, connections, merges, undo/redo.

The source graph and the user graph stay separated: user nodes carry
``is_user_created`` and survive regeneration; notes/colour/tags/flags on
source-derived nodes are re-attached after extraction. Every mutation is
snapshotted for exact undo/redo.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.graph.history import (
    HistoryError,
    push_history,
)
from mindweaver.graph.history import (
    redo as history_redo,
)
from mindweaver.graph.history import (
    undo as history_undo,
)
from mindweaver.graph.types import (
    GraphNode,
    GraphNodeType,
    normalize_edge_type,
    slugify,
)
from mindweaver.models import (
    Document,
    GraphEdgeRecord,
    GraphNodeRecord,
    GraphVersionRecord,
    NodeSourceRecord,
)


class EditError(Exception):
    pass


# --- internal helpers -----------------------------------------------------


def _record(session: Session, document_id: str, node_id: str) -> GraphNodeRecord:
    record = session.scalar(
        select(GraphNodeRecord).where(
            GraphNodeRecord.document_id == document_id,
            GraphNodeRecord.node_id == node_id,
        )
    )
    if record is None:
        raise EditError(f"node not found: {node_id}")
    return record


def _bump_version(session: Session, document_id: str, operation: str) -> int:
    version = (
        session.scalar(
            select(GraphVersionRecord.version)
            .where(GraphVersionRecord.document_id == document_id)
            .order_by(GraphVersionRecord.version.desc())
            .limit(1)
        )
        or 0
    ) + 1
    session.add(
        GraphVersionRecord(
            document_id=document_id,
            version=version,
            operation=operation,
            notes="[]",
        )
    )
    session.flush()
    return version


def _finish_mutation(session: Session, document: Document, action: str, operation: str) -> int:
    version = _bump_version(session, document.id, operation)
    from mindweaver.graph.history import seed_baseline  # noqa: F401  (import check)

    push_history(session, document, action)
    return version


def _loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return []


# --- mutations ------------------------------------------------------------


def add_personal_node(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    label: str,
    node_type: str = "concept",
    definition: str = "",
    note: str = "",
    color: str | None = None,
    tags: list[str] | None = None,
    is_important: bool = False,
    is_bookmarked: bool = False,
    ai_accepted: bool = False,
) -> GraphNode:
    if not label.strip():
        raise EditError("label must not be empty")
    raw_type = (node_type or "concept").strip().lower()
    if raw_type not in {member.value for member in GraphNodeType}:
        raise EditError(f"unknown node type: {node_type}")
    node_id = f"{raw_type}:{slugify(label)}"
    existing = session.scalar(
        select(GraphNodeRecord).where(
            GraphNodeRecord.document_id == document.id,
            GraphNodeRecord.node_id == node_id,
        )
    )
    if existing is not None:
        raise EditError(f"node already exists: {node_id}")

    record = GraphNodeRecord(
        document_id=document.id,
        node_id=node_id,
        label=label.strip(),
        node_type=raw_type,
        definition=definition,
        note=note,
        color=color,
        tags=json.dumps(tags or []),
        is_important=is_important,
        is_bookmarked=is_bookmarked,
        is_user_created=True,
        ai_accepted=ai_accepted,
    )
    session.add(record)
    session.flush()
    _finish_mutation(session, document, f"add node {node_id}", "user_edit:add_node")
    return _to_node(record, [])


def update_node(
    session: Session,
    settings: Settings,
    document: Document,
    node_id: str,
    updates: dict[str, Any],
) -> GraphNode:
    record = _record(session, document.id, node_id)

    if "label" in updates and updates["label"] is not None:
        label = str(updates["label"]).strip()
        if not label:
            raise EditError("label must not be empty")
        record.label = label
    if "note" in updates and updates["note"] is not None:
        record.note = str(updates["note"])
    if "color" in updates:
        record.color = updates["color"]
    if "tags" in updates and updates["tags"] is not None:
        tags = updates["tags"]
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise EditError("tags must be a list of strings")
        record.tags = json.dumps(tags)
    if "is_important" in updates and updates["is_important"] is not None:
        record.is_important = bool(updates["is_important"])
    if "is_bookmarked" in updates and updates["is_bookmarked"] is not None:
        record.is_bookmarked = bool(updates["is_bookmarked"])
    session.flush()

    _finish_mutation(session, document, f"update node {node_id}", "user_edit:update_node")
    return _to_node(record, _chunks_of(session, record.id))


def delete_node(session: Session, settings: Settings, document: Document, node_id: str) -> None:
    record = _record(session, document.id, node_id)
    session.execute(
        delete(GraphEdgeRecord).where(
            GraphEdgeRecord.document_id == document.id,
            (
                (GraphEdgeRecord.source_node_id == node_id)
                | (GraphEdgeRecord.target_node_id == node_id)
            ),
        )
    )
    session.delete(record)
    session.flush()
    _finish_mutation(session, document, f"delete node {node_id}", "user_edit:delete_node")


def create_connection(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    source: str,
    target: str,
    relation: str = "related_to",
    note: str = "",
) -> dict[str, Any]:
    if source == target:
        raise EditError("cannot connect a node to itself")
    resolved = normalize_edge_type(relation)
    if resolved is None:
        raise EditError(f"invalid relation: {relation}")
    _record(session, document.id, source)
    _record(session, document.id, target)

    duplicate = session.scalar(
        select(GraphEdgeRecord).where(
            GraphEdgeRecord.document_id == document.id,
            GraphEdgeRecord.source_node_id == source,
            GraphEdgeRecord.target_node_id == target,
            GraphEdgeRecord.relation == resolved.value,
        )
    )
    if duplicate is not None:
        raise EditError("connection already exists")

    edge = GraphEdgeRecord(
        document_id=document.id,
        source_node_id=source,
        target_node_id=target,
        relation=resolved.value,
        note=note,
        source_chunks="[]",
        is_inference=False,
        is_user_created=True,
    )
    session.add(edge)
    session.flush()
    _finish_mutation(
        session,
        document,
        f"connect {source} -{resolved.value}-> {target}",
        "user_edit:create_connection",
    )
    return {
        "source": source,
        "target": target,
        "relation": resolved.value,
        "note": note,
        "source_chunks": [],
        "is_inference": False,
        "is_user_created": True,
    }


def remove_connection(
    session: Session,
    settings: Settings,
    document: Document,
    *,
    source: str,
    target: str,
    relation: str,
) -> None:
    resolved = normalize_edge_type(relation)
    if resolved is None:
        raise EditError(f"invalid relation: {relation}")
    edge = session.scalar(
        select(GraphEdgeRecord).where(
            GraphEdgeRecord.document_id == document.id,
            GraphEdgeRecord.source_node_id == source,
            GraphEdgeRecord.target_node_id == target,
            GraphEdgeRecord.relation == resolved.value,
        )
    )
    if edge is None:
        raise EditError("connection not found")
    session.delete(edge)
    session.flush()
    _finish_mutation(
        session,
        document,
        f"remove {source} -{resolved.value}-> {target}",
        "user_edit:remove_connection",
    )


def merge_nodes(
    session: Session,
    settings: Settings,
    document: Document,
    node_id: str,
    into: str,
) -> GraphNode:
    """Merge ``node_id`` INTO ``into``: edges move, data unions, source goes away."""
    if node_id == into:
        raise EditError("cannot merge a node into itself")
    source_record = _record(session, document.id, node_id)
    target_record = _record(session, document.id, into)

    touching = session.scalars(
        select(GraphEdgeRecord).where(
            GraphEdgeRecord.document_id == document.id,
            (
                (GraphEdgeRecord.source_node_id == node_id)
                | (GraphEdgeRecord.target_node_id == node_id)
            ),
        )
    ).all()
    existing_keys = {
        (edge.source_node_id, edge.target_node_id, edge.relation)
        for edge in session.scalars(
            select(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document.id)
        ).all()
        if edge.source_node_id != node_id and edge.target_node_id != node_id
    }

    moved = 0
    seen_move_keys: set[tuple[str, str, str]] = set()
    for edge in touching:
        new_source = into if edge.source_node_id == node_id else edge.source_node_id
        new_target = into if edge.target_node_id == node_id else edge.target_node_id
        key = (new_source, new_target, edge.relation)
        if new_source == new_target or key in existing_keys or key in seen_move_keys:
            session.delete(edge)
            continue
        seen_move_keys.add(key)
        edge.source_node_id = new_source
        edge.target_node_id = new_target
        edge.is_user_created = True  # rewired by the user
        existing_keys.add(key)
        moved += 1

    # Union personal data.
    if not target_record.note and source_record.note:
        target_record.note = source_record.note
    elif source_record.note:
        target_record.note = f"{target_record.note}\n{source_record.note}".strip()
    target_tags = _loads(target_record.tags)
    for tag in _loads(source_record.tags):
        if tag not in target_tags:
            target_tags.append(tag)
    target_record.tags = json.dumps(target_tags)
    target_chunks = set(_chunks_of(session, target_record.id))
    source_chunks = set(_chunks_of(session, source_record.id))
    for chunk_id in source_chunks - target_chunks:
        session.add(
            NodeSourceRecord(node_id=target_record.id, chunk_id=chunk_id, page_start=0, page_end=0)
        )
    if not target_record.definition and source_record.definition:
        target_record.definition = source_record.definition
    target_record.is_important = target_record.is_important or source_record.is_important
    target_record.is_bookmarked = target_record.is_bookmarked or source_record.is_bookmarked
    if source_record.is_user_created:
        target_record.is_user_created = True

    session.delete(source_record)
    session.flush()
    _finish_mutation(
        session,
        document,
        f"merge {node_id} into {into} ({moved} edges moved)",
        "user_edit:merge",
    )
    return _to_node(target_record, _chunks_of(session, target_record.id))


def undo_last(session: Session, settings: Settings, document: Document) -> str:
    try:
        return history_undo(session, document)
    except HistoryError as exc:
        raise EditError(str(exc)) from exc


def redo_next(session: Session, settings: Settings, document: Document) -> str:
    try:
        return history_redo(session, document)
    except HistoryError as exc:
        raise EditError(str(exc)) from exc


# --- helpers --------------------------------------------------------------


def _chunks_of(session: Session, node_pk: str) -> list[str]:
    from mindweaver.models import NodeSourceRecord

    return [
        row[0].chunk_id
        for row in session.execute(
            select(NodeSourceRecord).where(NodeSourceRecord.node_id == node_pk)
        ).all()
    ]


def _to_node(record: GraphNodeRecord, source_chunks: list[str]) -> GraphNode:
    return GraphNode(
        id=record.node_id,
        label=record.label,
        type=GraphNodeType(record.node_type),
        definition=record.definition,
        source_chunks=source_chunks,
        note=record.note,
        color=record.color,
        tags=_loads(record.tags),
        is_important=record.is_important,
        is_bookmarked=record.is_bookmarked,
        is_user_created=record.is_user_created,
        ai_accepted=getattr(record, "ai_accepted", False),
    )
