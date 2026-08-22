"""Stage 4: vision escalation.

Vision is used ONLY when the existing pipeline flags a page as needing deeper
analysis (low OCR confidence, tables, diagrams, complex layout). The vision
model's interpretation is stored ALONGSIDE the original extraction — never
overwriting it.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from mindweaver.config import Settings
from mindweaver.intelligence.config import VisionAnalysisConfig
from mindweaver.ocr.base import OCRPageResult
from mindweaver.ocr.render import render_page

logger = logging.getLogger("intelligence.vision")


@dataclass
class VisionInterpretation:
    page_number: int
    content_type: str
    summary: str
    entities: list[str] = field(default_factory=list)
    relationships: list[list[str]] = field(default_factory=list)
    suggested_text: str | None = None
    confidence: float | None = None
    source: str = "vision_model"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "content_type": self.content_type,
            "summary": self.summary,
            "entities": self.entities,
            "relationships": self.relationships,
            "suggested_text": self.suggested_text,
            "confidence": self.confidence,
            "source": self.source,
        }


def select_pages(
    pages: list[dict[str, Any]],
    config: VisionAnalysisConfig,
) -> list[int]:
    """Pick pages that genuinely need vision analysis.

    ``pages`` items carry ``page_number``, ``confidence`` (may be None),
    ``has_table``, ``has_diagram``, ``text_length`` and ``extraction_method``.
    """
    selected: list[int] = []
    for page in pages:
        if not config.enabled and not config.analyze_all_pages:
            continue
        if config.analyze_all_pages:
            selected.append(page["page_number"])
            continue

        reasons = []
        confidence = page.get("confidence")
        triggers = config.triggers
        if (
            triggers.low_ocr_confidence
            and confidence is not None
            and confidence < config.confidence_threshold
        ):
            reasons.append("low_confidence")
        if triggers.tables and page.get("has_table"):
            reasons.append("table")
        if triggers.diagrams and page.get("has_diagram"):
            reasons.append("diagram")
        text_length = page.get("text_length", 0)
        if triggers.complex_layout and text_length < 40:
            reasons.append("low_text_density")
        if reasons:
            logger.info(
                "intelligence.vision.escalation page=%s reasons=%s",
                page["page_number"],
                reasons,
            )
            selected.append(page["page_number"])
    return selected


VISION_PROMPT = """Analyze this document page image. Respond ONLY with JSON:
{"page_number": <int>, "content_type": "<diagram|table|chart|text|mixed>",
 "summary": "<2-3 sentence summary>", "entities": ["..."],
 "relationships": [["A", "relation", "B"]],
 "suggested_text": "<transcribed key text or null>",
 "confidence": <0.0-1.0>}
Do not invent content you cannot see."""


def analyze_page(
    settings: Settings,
    intel_config: VisionAnalysisConfig,
    vision_model: Any,  # IntelligenceModel with vision capability
    pdf_path: str,
    page_number: int,
) -> VisionInterpretation:
    """Render one page, send it to the vision model, parse structured output."""

    image_bytes = render_page(pdf_path, page_number, scale=1.5)
    b64 = base64.b64encode(image_bytes).decode()

    response = vision_model.analyze_image(b64, VISION_PROMPT)
    text = response.content or ""
    try:
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start : end + 1])
    except Exception as exc:
        raise ValueError(f"vision model returned invalid JSON: {exc}") from exc

    return VisionInterpretation(
        page_number=page_number,
        content_type=str(parsed.get("content_type") or "unknown"),
        summary=str(parsed.get("summary") or ""),
        entities=[str(e) for e in parsed.get("entities") or []],
        relationships=[
            [str(part) for part in rel]
            for rel in parsed.get("relationships") or []
            if isinstance(rel, list)
        ],
        suggested_text=parsed.get("suggested_text"),
        confidence=float(parsed["confidence"]) if parsed.get("confidence") is not None else None,
    )


def escalate_with_fallback(
    settings: Settings,
    intel_config: VisionAnalysisConfig,
    vision_model: Any,
    pdf_path: str,
    page_number: int,
    ocr_result: OCRPageResult | None,
) -> tuple[VisionInterpretation | None, str]:
    """Try vision; on any failure preserve the existing result and return a
    feature-specific error instead of crashing."""
    try:
        interpretation = analyze_page(settings, intel_config, vision_model, pdf_path, page_number)
        return interpretation, ""
    except Exception as exc:
        message = f"vision analysis unavailable for page {page_number}: {exc}"
        logger.warning("intelligence.vision.skip %s", message)
        preserved = ocr_result.text[:200] if ocr_result is not None else "(no OCR result)"
        return None, f"{message}; preserved extraction: {preserved!r}"


def save_interpretation(settings: Settings, document_id: str, interp: VisionInterpretation) -> None:
    """Store the interpretation next to (never over) the original extraction."""
    from mindweaver import storage

    storage.save_derived_json(
        settings,
        document_id,
        f"vision/page_{interp.page_number}.json",
        json.dumps(interp.to_dict(), indent=2),
    )
