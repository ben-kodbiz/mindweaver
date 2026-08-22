"""SQLite FTS5 keyword index and search.

The FTS virtual table mirrors the ``chunks`` table: chunk text, chapter,
section, section path, and document title are indexed.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from mindweaver.models import ChunkRecord

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    page_start UNINDEXED,
    page_end UNINDEXED,
    chapter,
    section,
    section_path,
    text,
    tokenize = 'porter unicode61'
)
"""

_WORD_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)


def ensure_fts(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(_FTS_DDL))


def build_match_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (AND of quoted words)."""
    words = _WORD_RE.findall(query or "")
    if not words:
        return ""
    return " AND ".join(f'"{word}"' for word in words)


def index_document(session: Session, records: list[ChunkRecord]) -> None:
    """Replace FTS rows for a document with the given chunk records."""
    if not records:
        return
    session.execute(
        text("DELETE FROM chunks_fts WHERE document_id = :document_id"),
        {"document_id": records[0].document_id},
    )
    for record in records:
        session.execute(
            text(
                "INSERT INTO chunks_fts "
                "(chunk_id, document_id, page_start, page_end, chapter, section, "
                " section_path, text) "
                "VALUES (:chunk_id, :document_id, :page_start, :page_end, :chapter, "
                ":section, :section_path, :text)"
            ),
            {
                "chunk_id": record.chunk_id,
                "document_id": record.document_id,
                "page_start": record.page_start,
                "page_end": record.page_end,
                "chapter": record.chapter,
                "section": record.section,
                "section_path": " ".join(_json_loads(record.section_path)),
                "text": record.text,
            },
        )


def _json_loads(value: str) -> list[str]:
    import json
    from typing import cast as _cast

    try:
        return _cast(list[str], json.loads(value))
    except Exception:
        return []


def keyword_search(
    session: Session,
    query: str,
    *,
    document_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return top keyword hits as ``{chunk_id, score}`` (score closer to 0 is better)."""
    match = build_match_query(query)
    if not match:
        return []

    where = ["chunks_fts MATCH :match"]
    params: dict[str, Any] = {"match": match, "limit": limit}
    if document_id is not None:
        where.append("document_id = :document_id")
        params["document_id"] = document_id

    rows = (
        session.execute(
            text(
                "SELECT chunk_id, bm25(chunks_fts, 5.0, 1.0, 1.0, 1.0, 1.0, 1.0) AS score "
                f"FROM chunks_fts WHERE {' AND '.join(where)} "
                "ORDER BY score LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [{"chunk_id": row["chunk_id"], "score": float(row["score"])} for row in rows]
