"""Structural chunking.

Chunks follow the document's section hierarchy rather than fixed token
windows: blocks are grouped by their section, contextual section headers are
prepended, and only oversized sections are split (never mid-paragraph, and
never splitting a table or separating a caption from its content).
"""

from __future__ import annotations

import re

from mindweaver.chunking.model import Chunk
from mindweaver.document_model import BlockType, CanonicalDocument, ContentBlock

_HEADING_TITLE = re.compile(r"^#{1,6}\s+")


def _token_count(text: str) -> int:
    return len(text.split())


def _group_blocks(doc: CanonicalDocument) -> list[tuple[tuple[str, ...], list[ContentBlock]]]:
    """Group content blocks by their section path, preserving document order."""

    groups: dict[tuple[str, ...], list[ContentBlock]] = {}
    order: list[tuple[str, ...]] = []
    for block in doc.blocks:
        path = tuple(block.section_path)
        if path not in groups:
            groups[path] = []
            order.append(path)
        groups[path].append(block)
    return [(path, groups[path]) for path in order]


def _context_header(path: tuple[str, ...]) -> str:
    if not path:
        return ""
    return "\n".join(path)


def _merge_captions(path: tuple[str, ...], blocks: list[ContentBlock]) -> list[str]:
    """Return text units with captions attached to their related content.

    Heading blocks whose text repeats the section header are dropped since
    the header is already prepended as context.
    """
    units: list[str] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if block.block_type in (BlockType.HEADING, BlockType.TITLE) and text == (
            path[-1] if path else None
        ):
            continue
        if block.block_type == BlockType.CAPTION and units:
            units[-1] = f"{units[-1]}\n{text}"
        else:
            units.append(text)
    return units


def _split_paragraph(text: str, max_chars: int) -> list[str]:
    """Split a single oversized paragraph on sentence boundaries."""

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [text]


def _split_units(units: list[str], header: str, max_chars: int, min_chars: int) -> list[str]:
    """Group text units into chunk texts up to ``max_chars``.

    A unit (paragraph/table/merged caption) is never split; only an oversized
    paragraph is split on sentence boundaries.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append(_join(header, current))
            current = []
            current_len = 0

    for unit in units:
        unit_len = len(unit)
        if current and current_len + unit_len > max_chars:
            flush()
        if unit_len > max_chars:
            parts = _split_paragraph(unit, max_chars) if _is_paragraph_unit(unit) else [unit]
            for part in parts:
                if current and current_len + len(part) > max_chars:
                    flush()
                current.append(part)
                current_len += len(part)
        else:
            current.append(unit)
            current_len += unit_len
    flush()

    # Merge tiny trailing chunks back if beneficial and within limits.
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(chunk) < min_chars and len(merged[-1]) + len(chunk) <= max_chars:
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)
    return merged or ([""] if chunks or units else [])


def _is_paragraph_unit(unit: str) -> bool:
    return "\t" not in unit


def _join(header: str, parts: list[str]) -> str:
    body = "\n\n".join(parts).strip()
    if header:
        return f"{header}\n\n{body}"
    return body


def chunk_document(
    doc: CanonicalDocument, *, max_chars: int = 2000, min_chars: int = 100
) -> list[Chunk]:
    """Split a canonical document into structural chunks."""

    chunks: list[Chunk] = []
    parent_ids: dict[tuple[str, ...], str] = {}

    groups = _group_blocks(doc)
    # Compute parent chunk ids for nested sections (parent path precedes child
    # in document order because outline preorder == reading order).
    index = 0
    for path, blocks in groups:
        header = _context_header(path)
        units = _merge_captions(path, blocks)
        texts = _split_units(units, header, max_chars, min_chars)
        if not texts:
            continue

        page_numbers = [block.page_number for block in blocks]
        page_start = min(page_numbers) if page_numbers else 0
        page_end = max(page_numbers) if page_numbers else 0

        parent_chunk_id = parent_ids.get(path[:-1])
        first_id: str | None = None
        for part_index, text in enumerate(texts):
            chunk_id = f"chk_{doc.document_id}_{index}"
            index += 1
            if first_id is None:
                first_id = chunk_id
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=doc.document_id,
                    page_start=page_start,
                    page_end=page_end,
                    chapter=path[0] if len(path) > 0 else None,
                    section=path[1] if len(path) > 1 else None,
                    subsection=path[2] if len(path) > 2 else None,
                    section_path=list(path),
                    text=text,
                    token_count=_token_count(text),
                    parent_chunk_id=parent_chunk_id,
                    metadata={
                        "part": part_index,
                        "split": len(texts) > 1,
                        "source_blocks": len(blocks),
                    },
                )
            )
        parent_ids[path] = first_id or ""

    return chunks
