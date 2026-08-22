"""Native (pypdf) document processor.

Lightweight fallback that extracts per-page text with page numbers and uses
the PDF outline (bookmarks) to reconstruct chapter/section hierarchy. It does
not detect tables/figures semantically; use the Docling processor for full
layout intelligence.

When an :class:`OCRPipeline` is attached (hybrid backend), scanned pages are
rendered and OCR'd; otherwise scanned pages set ``requires_ocr`` so the caller
can mark the document ``OCR_REQUIRED``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from mindweaver.document_model import (
    BlockType,
    CanonicalDocument,
    ContentBlock,
    Page,
    Section,
)
from mindweaver.extraction.base import DocumentProcessor, ExtractionError, ExtractionResult
from mindweaver.extraction.page_inspector import PageContentType, inspect_pages
from mindweaver.ocr.pipeline import OCRPipeline

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text or "").strip()


@dataclass
class _OutlineNode:
    title: str
    page_no: int
    level: int = 1
    children: list[_OutlineNode] = field(default_factory=list)


@dataclass
class _HeadingState:
    cursor: int = 0
    stack: list[Section] = field(default_factory=list)


class PyPdfProcessor(DocumentProcessor):
    name = "pypdf"

    def __init__(self, ocr_pipeline: OCRPipeline | None = None) -> None:
        self.ocr_pipeline = ocr_pipeline

    def extract(self, path: Path, *, document_id: str, filename: str) -> ExtractionResult:
        try:
            reader = PdfReader(str(path), strict=False)
        except Exception as exc:
            raise ExtractionError(f"could not read PDF: {exc}") from exc
        if reader.is_encrypted:
            raise ExtractionError("password-protected PDFs are not supported yet")

        warnings: list[str] = []
        requires_ocr = False
        outline = self._parse_outline(reader)
        flat_headings = self._flatten_outline(outline)
        inspections = inspect_pages(reader)

        pages: list[Page] = []
        for page_no, page in enumerate(reader.pages, start=1):
            width = page.mediabox.width
            height = page.mediabox.height
            pages.append(
                Page(
                    page_number=page_no,
                    width=float(width) if width is not None else None,
                    height=float(height) if height is not None else None,
                )
            )

        sections: list[Section] = []
        section_by_title: dict[str, Section] = {}
        self._build_sections(outline, sections, section_by_title)

        blocks: list[ContentBlock] = []
        heading_state = _HeadingState()
        for page_no, page in enumerate(reader.pages, start=1):
            inspection = inspections[page_no - 1]
            if inspection.content_type == PageContentType.SCANNED:
                requires_ocr = requires_ocr or self.ocr_pipeline is None
                if self.ocr_pipeline is None:
                    pages[page_no - 1].extraction_method = "ocr"
                    pages[page_no - 1].low_confidence = True
                    continue
                ocr_result = self.ocr_pipeline.ocr_page(path, document_id, page_no)
                pages[page_no - 1].extraction_method = "ocr"
                pages[page_no - 1].confidence = ocr_result.confidence
                pages[page_no - 1].low_confidence = ocr_result.low_confidence
                self._emit_units(
                    page_no=page_no,
                    units=[word.text for word in ocr_result.words] or [ocr_result.text],
                    document_id=document_id,
                    blocks=blocks,
                    flat_headings=flat_headings,
                    heading_state=heading_state,
                    section_by_title=section_by_title,
                    confidence_by_text={word.text: word.confidence for word in ocr_result.words},
                )
                continue

            try:
                raw = page.extract_text(extraction_mode="layout") or ""
            except Exception:
                raw = ""
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            self._emit_units(
                page_no=page_no,
                units=paragraphs,
                document_id=document_id,
                blocks=blocks,
                flat_headings=flat_headings,
                heading_state=heading_state,
                section_by_title=section_by_title,
                confidence_by_text={},
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
            metadata={
                "extraction_warnings": warnings,
                "extraction_method": "native",
                "page_inspections": [
                    {
                        "page_number": inspection.page_number,
                        "content_type": inspection.content_type.value,
                        "text_length": inspection.text_length,
                        "has_images": inspection.has_images,
                    }
                    for inspection in inspections
                ],
            },
        )
        return ExtractionResult(document=document, warnings=warnings, requires_ocr=requires_ocr)

    def _emit_units(
        self,
        *,
        page_no: int,
        units: list[str],
        document_id: str,
        blocks: list[ContentBlock],
        flat_headings: list[_OutlineNode],
        heading_state: _HeadingState,
        section_by_title: dict[str, Section],
        confidence_by_text: dict[str, float],
    ) -> None:
        """Emit blocks for text units, advancing the heading stack on matches.

        ``heading_state`` (cursor + stack) is mutated in place so multiple
        calls share heading state across pages.
        """
        for unit in units:
            if not unit.strip():
                continue
            normalized = _normalize(unit)
            is_heading = False
            while heading_state.cursor < len(flat_headings):
                node = flat_headings[heading_state.cursor]
                if node.page_no > page_no:
                    break
                if _normalize(node.title) != normalized:
                    break
                section = section_by_title[_normalize(node.title)]
                while heading_state.stack and heading_state.stack[-1].level >= section.level:
                    heading_state.stack.pop()
                heading_state.stack.append(section)
                heading_state.cursor += 1
                is_heading = True
                break

            section_path = [sec.title for sec in heading_state.stack]
            blocks.append(
                ContentBlock(
                    block_id=f"blk_{document_id}_{page_no}_{len(blocks)}",
                    document_id=document_id,
                    page_number=page_no,
                    block_type=BlockType.HEADING if is_heading else BlockType.PARAGRAPH,
                    text=unit,
                    section_path=section_path,
                    source_confidence=confidence_by_text.get(unit),
                )
            )

    # --- outline handling -------------------------------------------------

    def _page_of(self, reader: PdfReader, entry: object) -> int | None:
        try:
            page_no = reader.get_destination_page_number(entry)  # type: ignore[arg-type]
            if page_no is not None:
                return page_no + 1
        except Exception:
            pass
        page = getattr(entry, "page", None)
        if isinstance(page, int):
            return page + 1
        if page is not None:
            try:
                page_no = reader.get_page_number(page)
                if page_no is not None:
                    return page_no + 1
            except Exception:
                return None
        return None

    def _parse_outline(self, reader: PdfReader) -> list[_OutlineNode]:
        """Parse the outline into a tree.

        pypdf represents hierarchy in two ways: nested lists following a
        destination (``[title, [children...]]``) for most PDFs, or via the
        destination's ``children()`` method for outlines written by pypdf.
        Both are handled here.
        """

        def parse(entries: object, level: int) -> list[_OutlineNode]:
            nodes: list[_OutlineNode] = []
            if not isinstance(entries, list):
                return nodes
            for entry in entries:
                if isinstance(entry, list):
                    if nodes:
                        nodes[-1].children = parse(entry, level + 1)
                    continue
                if not (hasattr(entry, "title") and getattr(entry, "title", None)):
                    continue
                page_no = self._page_of(reader, entry)
                if page_no is None:
                    continue
                node = _OutlineNode(
                    title=str(entry.title).strip(),
                    page_no=page_no,
                    level=level,
                )
                children_attr = getattr(entry, "children", None)
                children = children_attr() if callable(children_attr) else children_attr
                children = list(children or [])
                if children:
                    node.children = parse(children, level + 1)
                nodes.append(node)
            return nodes

        return parse(reader.outline, 1)

    def _flatten_outline(self, nodes: list[_OutlineNode]) -> list[_OutlineNode]:
        """Outline preorder = document reading order (no re-sorting)."""
        flat: list[_OutlineNode] = []

        def walk(node: _OutlineNode) -> None:
            flat.append(node)
            for child in node.children:
                walk(child)

        for node in nodes:
            walk(node)
        return flat

    def _build_sections(
        self,
        nodes: list[_OutlineNode],
        sections: list[Section],
        section_by_title: dict[str, Section],
    ) -> None:
        def walk(node: _OutlineNode, stack: list[Section]) -> None:
            section = Section(
                id=f"sec_{len(section_by_title)}",
                title=node.title,
                level=node.level,
                page_number=node.page_no,
                section_path=[sec.title for sec in stack] + [node.title],
            )
            parent = stack[-1] if stack else None
            if parent is not None:
                parent.children.append(section)
            else:
                sections.append(section)
            section_by_title[_normalize(node.title)] = section
            for child in node.children:
                walk(child, stack + [section])

        for node in nodes:
            walk(node, [])
