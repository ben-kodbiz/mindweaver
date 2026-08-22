"""Docling document processor.

Full layout intelligence: heading/section hierarchy, tables, figures,
captions, footnotes, and bounding boxes. Docling is an optional dependency
(``[docling]`` extra); import it lazily so the rest of the app works without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mindweaver.document_model import (
    BlockType,
    BoundingBox,
    CanonicalDocument,
    ContentBlock,
    Page,
    Section,
)
from mindweaver.extraction.base import DocumentProcessor, ExtractionError, ExtractionResult

_TEXT_LABEL_TO_BLOCK: dict[str, BlockType] = {
    "title": BlockType.TITLE,
    "section_header": BlockType.HEADING,
    "text": BlockType.PARAGRAPH,
    "paragraph": BlockType.PARAGRAPH,
    "list_item": BlockType.LIST_ITEM,
    "caption": BlockType.CAPTION,
    "footnote": BlockType.FOOTNOTE,
    "formula": BlockType.FORMULA,
    "code": BlockType.OTHER,
}

_BLOCK_TO_BLOCKTYPE: dict[str, BlockType] = {
    "text": BlockType.PARAGRAPH,
    "table": BlockType.TABLE,
    "picture": BlockType.FIGURE,
    "checkbox": BlockType.OTHER,
    "form": BlockType.OTHER,
}


class DoclingProcessor(DocumentProcessor):
    name = "docling"

    def extract(self, path: Path, *, document_id: str, filename: str) -> ExtractionResult:
        from docling.document_converter import DocumentConverter

        warnings: list[str] = []
        try:
            result = DocumentConverter().convert(str(path))
        except Exception as exc:
            raise ExtractionError(f"docling conversion failed: {exc}") from exc
        dl_document = result.document

        pages: list[Page] = []
        for page_no in sorted(dl_document.pages.keys()):
            page = dl_document.pages[page_no]
            size = getattr(page, "size", None)
            pages.append(
                Page(
                    page_number=page_no,
                    width=float(size.width) if size else None,
                    height=float(size.height) if size else None,
                )
            )

        sections: list[Section] = []
        blocks: list[ContentBlock] = []
        counter: dict[str, int] = {}
        heading_levels = self._heading_levels(dl_document)
        self._walk(
            dl_document,
            dl_document.body.children,
            sections=sections,
            blocks=blocks,
            document_id=document_id,
            counter=counter,
            warnings=warnings,
            heading_levels=heading_levels,
        )

        if not pages:
            raise ExtractionError("PDF contains no pages")

        document = CanonicalDocument(
            document_id=document_id,
            source_filename=filename,
            processor=self.name,
            pages=pages,
            sections=sections,
            blocks=blocks,
            metadata={"extraction_warnings": warnings, "extraction_method": "native"},
        )
        return ExtractionResult(document=document, warnings=warnings)

    def _walk(
        self,
        dl_document: Any,
        refs: Any,
        *,
        sections: list[Section],
        blocks: list[ContentBlock],
        document_id: str,
        counter: dict[str, int],
        warnings: list[str],
        heading_levels: dict[str, int],
    ) -> None:
        """Build sections and blocks from Docling's content items.

        Docling exposes body children in reading order. Section nesting is
        reconstructed with a stack using inferred heading levels (from font
        size tiers); each block receives the section path of the active stack.
        """
        stack: list[Section] = []

        def visit(ref: Any) -> None:
            item = self._resolve(dl_document, ref)
            if item is None:
                return
            label = getattr(item, "label", None)
            label_value = getattr(label, "value", None) or getattr(label, "name", None)
            children = getattr(item, "children", None)

            if label_value == "section_header":
                title = (getattr(item, "text", None) or "").strip()
                level = heading_levels.get(title, 1)
                while stack and stack[-1].level >= level:
                    stack.pop()
                section = Section(
                    id=self._next_id(counter, document_id, "sec"),
                    title=title,
                    level=level,
                    page_number=self._page_of(item),
                    section_path=[entry.title for entry in stack] + [title],
                )
                if stack:
                    stack[-1].children.append(section)
                else:
                    sections.append(section)
                stack.append(section)
                return

            if label_value in ("page_header", "page_footer"):
                return

            block_type = _BLOCK_TO_BLOCKTYPE.get(
                label_value or "", _TEXT_LABEL_TO_BLOCK.get(label_value or "", BlockType.OTHER)
            )
            text = getattr(item, "text", None) or ""
            block = ContentBlock(
                block_id=self._next_id(counter, document_id, "blk"),
                document_id=document_id,
                page_number=self._page_of(item),
                block_type=block_type,
                text=text.strip() if isinstance(text, str) else str(text),
                section_path=[entry.title for entry in stack],
                bbox=self._bbox_of(item),
                source_confidence=self._confidence_of(item),
            )
            if label_value == "table":
                block.table_rows = self._table_rows(item)
                block.text = "\n".join("\t".join(row) for row in block.table_rows)
            elif label_value == "picture":
                block.figure_ref = getattr(item, "name", None)
            blocks.append(block)

            for child in children or []:
                visit(child)

        for ref in refs or []:
            visit(ref)

    def _heading_levels(self, dl_document: Any) -> dict[str, int]:
        """Infer heading levels from font-size tiers.

        Docling's ``level``/markdown export is often flat, so heading depth is
        derived from the rendered font size (bbox height) of section headers:
        the largest size tier is level 1, each smaller distinct tier goes one
        level deeper.
        """
        sizes: dict[str, float] = {}
        for ref in dl_document.body.children or []:
            item = self._resolve(dl_document, ref)
            if item is None:
                continue
            label = getattr(item, "label", None)
            if getattr(label, "value", None) != "section_header":
                continue
            title = (getattr(item, "text", None) or "").strip()
            if not title:
                continue
            bbox = getattr(getattr(item, "prov", [None])[0], "bbox", None)
            if bbox is None:
                continue
            sizes[title] = round(float(bbox.t) - float(bbox.b), 1)

        distinct = sorted(set(sizes.values()), reverse=True)
        tiers = {size: index + 1 for index, size in enumerate(distinct)}
        return {title: tiers[size] for title, size in sizes.items()}

    def _resolve(self, dl_document: Any, ref: Any) -> Any | None:
        try:
            return ref.resolve(dl_document)
        except Exception:
            return None

    def _next_id(self, counter: dict[str, int], document_id: str, prefix: str) -> str:
        index = counter.get(prefix, 0)
        counter[prefix] = index + 1
        return f"{prefix}_{index}"

    def _page_of(self, item: Any) -> int:
        prov = getattr(item, "prov", None)
        if prov:
            return int(getattr(prov[0], "page_no", 1))
        return 1

    def _bbox_of(self, item: Any) -> BoundingBox | None:
        prov = getattr(item, "prov", None)
        if not prov:
            return None
        bbox = getattr(prov[0], "bbox", None)
        if bbox is None:
            return None
        return BoundingBox(
            page_number=self._page_of(item),
            left=float(bbox.l),
            top=float(bbox.t),
            right=float(bbox.r),
            bottom=float(bbox.b),
        )

    def _confidence_of(self, item: Any) -> float | None:
        prov = getattr(item, "prov", None)
        if not prov:
            return None
        confidence = getattr(prov[0], "confidence", None)
        return float(confidence) if confidence is not None else None

    def _table_rows(self, item: Any) -> list[list[str]]:
        try:
            frame = item.export_to_dataframe()
            rows = frame.astype(str).values.tolist()
            return [[cell if cell != "nan" else "" for cell in row] for row in rows]
        except Exception:
            return []
