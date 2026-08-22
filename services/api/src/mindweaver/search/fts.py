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

# Ubiquitous function words carry almost no relevance signal; keeping them in
# a relaxed OR query lets stopword-only matches crowd out real ones.
_STOPWORDS = frozenset(
    [
        "a", "an", "the", "and", "or", "of", "to", "in",
        "on", "for", "with", "is", "are", "was", "were", "be",
        "been", "being", "am", "this", "that", "these", "those", "it",
        "its", "as", "at", "by", "from", "into", "than", "then",
        "there", "here", "what", "which", "who", "whom", "whose", "when",
        "where", "why", "how", "do", "does", "did", "done", "doing",
        "can", "could", "should", "would", "shall", "will", "may", "might",
        "must", "have", "has", "had", "having", "i", "you", "he",
        "she", "we", "they", "him", "her", "them", "his", "hers",
        "their", "our", "your", "my", "me", "us", "if", "because",
        "while", "about", "above", "after", "again", "against", "all", "any",
        "before", "below", "between", "both", "down", "during", "each", "few",
        "further", "more", "most", "no", "nor", "not", "off", "once",
        "only", "other", "out", "own", "same", "some", "such", "through",
        "too", "under", "until", "up", "very", "according", "also",
    ]
)


def ensure_fts(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(_FTS_DDL))


def build_match_query(query: str, *, operator: str = "AND") -> str:
    """Turn free text into a safe FTS5 MATCH expression of quoted words."""
    words = _WORD_RE.findall(query or "")
    if not words:
        return ""
    return f" {operator} ".join(f'"{word}"' for word in words)


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
    document_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return top keyword hits as ``{chunk_id, score}`` (score closer to 0 is better)."""
    match = build_match_query(query)
    if not match:
        return []

    where = ["chunks_fts MATCH :match"]
    params: dict[str, Any] = {"match": match, "limit": limit}
    if document_ids:
        placeholders = ", ".join(f":doc_id_{i}" for i in range(len(document_ids)))
        where.append(f"document_id IN ({placeholders})")
        for i, doc_id in enumerate(document_ids):
            params[f"doc_id_{i}"] = doc_id
    elif document_id is not None:
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
    if not rows:
        # Natural-language questions rarely contain every term verbatim in one
        # chunk, so a strict AND often matches nothing. Fall back to an OR of
        # the content words: bm25 still ranks chunks matching more/rarer terms
        # first, which recovers recall for conversational queries.
        or_words = [w for w in _WORD_RE.findall(query) if w.lower() not in _STOPWORDS]
        if not or_words:
            return []
        or_match = " OR ".join(f'"{word}"' for word in or_words)
        params["match"] = or_match
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
