"""Graph edit history: full-state snapshots with undo/redo.

Every user edit pushes a complete snapshot of the document graph (source AND
user layer), so undo/restore is exact regardless of how many fields an action
touched. Extraction/expansion reset the history: undo/redo covers user edits,
not LLM regenerations.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mindweaver.models import (
    Document,
    GraphEdgeRecord,
    GraphHistoryEntry,
    GraphHistoryState,
    GraphNodeRecord,
    NodeSourceRecord,
)


class HistoryError(Exception):
    pass


def snapshot_from_records(session: Session, document_id: str) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for record in session.scalars(
        select(GraphNodeRecord).where(GraphNodeRecord.document_id == document_id)
    ).all():
        source_chunks = [
            row[0].chunk_id
            for row in session.execute(
                select(NodeSourceRecord).where(NodeSourceRecord.node_id == record.id)
            ).all()
        ]
        nodes.append(
            {
                "node_id": record.node_id,
                "label": record.label,
                "node_type": record.node_type,
                "definition": record.definition,
                "note": record.note,
                "color": record.color,
                "tags": _loads(record.tags),
                "is_important": record.is_important,
                "is_bookmarked": record.is_bookmarked,
                "is_user_created": record.is_user_created,
                "source_chunks": source_chunks,
            }
        )

    edges = [
        {
            "source_node_id": record.source_node_id,
            "target_node_id": record.target_node_id,
            "relation": record.relation,
            "note": record.note,
            "source_chunks": _loads(record.source_chunks),
            "is_inference": record.is_inference,
            "is_user_created": record.is_user_created,
        }
        for record in session.scalars(
            select(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document_id)
        ).all()
    ]
    return {"nodes": nodes, "edges": edges}


def _dumps(value: Any) -> str:
    return json.dumps(value)


def _loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return []


def _get_pointer(session: Session, document_id: str) -> int:
    state = session.get(GraphHistoryState, document_id)
    if state is None:
        return -1  # no baseline yet
    return state.position


def _set_pointer(session: Session, document_id: str, position: int) -> None:
    state = session.get(GraphHistoryState, document_id)
    if state is None:
        session.add(GraphHistoryState(document_id=document_id, position=position))
    else:
        state.position = position
    session.flush()


def seed_baseline(session: Session, document: Document) -> None:
    """Reset history and store the current graph as position 0."""
    session.execute(delete(GraphHistoryEntry).where(GraphHistoryEntry.document_id == document.id))
    session.execute(delete(GraphHistoryState).where(GraphHistoryState.document_id == document.id))
    entry = GraphHistoryEntry(
        document_id=document.id,
        position=0,
        action="baseline",
        snapshot=_dumps(snapshot_from_records(session, document.id)),
    )
    session.add(entry)
    _set_pointer(session, document.id, 0)
    session.flush()


def push_history(session: Session, document: Document, action: str) -> int:
    """Store the current (post-mutation) state as a new history entry."""
    pointer = _get_pointer(session, document.id)
    session.execute(
        delete(GraphHistoryEntry).where(
            GraphHistoryEntry.document_id == document.id,
            GraphHistoryEntry.position > pointer,
        )
    )
    entry = GraphHistoryEntry(
        document_id=document.id,
        position=pointer + 1,
        action=action,
        snapshot=_dumps(snapshot_from_records(session, document.id)),
    )
    session.add(entry)
    _set_pointer(session, document.id, pointer + 1)
    session.flush()
    return pointer + 1


def _entry_at(session: Session, document_id: str, position: int) -> GraphHistoryEntry | None:
    return session.scalar(
        select(GraphHistoryEntry).where(
            GraphHistoryEntry.document_id == document_id,
            GraphHistoryEntry.position == position,
        )
    )


def _max_position(session: Session, document_id: str) -> int:
    value = session.scalar(
        select(func.max(GraphHistoryEntry.position)).where(
            GraphHistoryEntry.document_id == document_id
        )
    )
    return int(value) if value is not None else -1


def restore_snapshot(session: Session, document_id: str, snapshot: dict[str, Any]) -> None:
    """Rebuild the entire stored graph exactly from a snapshot.

    Does not touch versions or history pointers.
    """
    session.execute(delete(GraphEdgeRecord).where(GraphEdgeRecord.document_id == document_id))
    session.execute(delete(GraphNodeRecord).where(GraphNodeRecord.document_id == document_id))

    id_to_pk: dict[str, str] = {}
    for item in snapshot["nodes"]:
        record = GraphNodeRecord(
            document_id=document_id,
            node_id=item["node_id"],
            label=item["label"],
            node_type=item["node_type"],
            definition=item.get("definition", ""),
            note=item.get("note", ""),
            color=item.get("color"),
            tags=_dumps(item.get("tags", [])),
            is_important=item.get("is_important", False),
            is_bookmarked=item.get("is_bookmarked", False),
            is_user_created=item.get("is_user_created", False),
            ai_accepted=item.get("ai_accepted", False),
        )
        session.add(record)
        session.flush()
        id_to_pk[item["node_id"]] = record.id
        for chunk_id in item.get("source_chunks", []):
            session.add(
                NodeSourceRecord(node_id=record.id, chunk_id=chunk_id, page_start=0, page_end=0)
            )

    for item in snapshot["edges"]:
        session.add(
            GraphEdgeRecord(
                document_id=document_id,
                source_node_id=item["source_node_id"],
                target_node_id=item["target_node_id"],
                relation=item["relation"],
                note=item.get("note", ""),
                source_chunks=_dumps(item.get("source_chunks", [])),
                is_inference=item.get("is_inference", False),
                is_user_created=item.get("is_user_created", False),
            )
        )
    session.flush()


def undo(session: Session, document: Document) -> str:
    """Restore the previous state. Returns the undone action's name."""
    pointer = _get_pointer(session, document.id)
    if pointer <= 0:
        raise HistoryError("nothing to undo")
    entry = _entry_at(session, document.id, pointer)
    current_action = entry.action if entry else f"step {pointer}"
    previous = _entry_at(session, document.id, pointer - 1)
    if previous is None:
        raise HistoryError("nothing to undo")
    restore_snapshot(session, document.id, json.loads(previous.snapshot))
    _set_pointer(session, document.id, pointer - 1)
    return current_action


def redo(session: Session, document: Document) -> str:
    """Re-apply the next state. Returns the redone action's name."""
    pointer = _get_pointer(session, document.id)
    if pointer >= _max_position(session, document.id):
        raise HistoryError("nothing to redo")
    nxt = _entry_at(session, document.id, pointer + 1)
    if nxt is None:
        raise HistoryError("nothing to redo")
    restore_snapshot(session, document.id, json.loads(nxt.snapshot))
    _set_pointer(session, document.id, pointer + 1)
    return nxt.action
