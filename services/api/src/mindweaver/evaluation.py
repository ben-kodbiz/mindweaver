"""Stage 21: full evaluation framework.

Extends the Stage-6 retrieval evaluation with mind-map quality metrics
(source coverage, duplicates, invalid relationships, orphans) and OCR
accuracy metrics (character/word accuracy, page confidence).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mindweaver.ocr.base import OCRPageResult

from mindweaver.graph.types import GraphRead

# --- mind map / graph quality ---------------------------------------------


@dataclass
class GraphQualityReport:
    total_nodes: int = 0
    duplicate_nodes: int = 0
    orphan_nodes: int = 0
    invalid_relationships: int = 0
    source_coverage: float = 1.0
    hierarchy_quality: float = 1.0
    issues: list[str] = field(default_factory=list)


def evaluate_graph(graph: GraphRead) -> GraphQualityReport:
    report = GraphQualityReport(total_nodes=len(graph.nodes))

    seen_labels: dict[tuple[str, str], str] = {}
    for node in graph.nodes:
        key = (node.type.value, re.sub(r"\s+", " ", node.label.lower()).strip())
        if key in seen_labels:
            report.duplicate_nodes += 1
            report.issues.append(
                f"duplicate label '{node.label}' ({node.id} vs {seen_labels[key]})"
            )
        else:
            seen_labels[key] = node.id

    connected: set[str] = set()
    for edge in graph.edges:
        connected.add(edge.source)
        connected.add(edge.target)
        if edge.source == edge.target:
            report.invalid_relationships += 1
            report.issues.append(f"self loop on {edge.source}")
        if not edge.source_chunks and not edge.is_inference:
            report.invalid_relationships += 1
            report.issues.append(
                f"edge {edge.source}->{edge.target} has no evidence and is not marked inference"
            )
    orphans = [node.id for node in graph.nodes if node.id not in connected]
    report.orphan_nodes = len(orphans)

    covered = sum(1 for node in graph.nodes if node.source_chunks)
    if graph.nodes:
        report.source_coverage = covered / len(graph.nodes)

    # hierarchy quality: share of nodes that are concepts/topics with evidence
    meaningful = [n for n in graph.nodes if n.type.value in ("concept", "topic", "claim")]
    if graph.nodes:
        report.hierarchy_quality = len(meaningful) / len(graph.nodes)

    return report


# --- OCR accuracy ----------------------------------------------------------


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def character_accuracy(reference: str, hypothesis: str) -> float:
    """Levenshtein-based character accuracy in [0, 1]."""
    ref = _normalise(reference)
    hyp = _normalise(hypothesis)
    if not ref:
        return 1.0 if not hyp else 0.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        current = [i]
        for j, h in enumerate(hyp, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    distance = previous[-1]
    return max(0.0, 1.0 - distance / len(ref))


def word_accuracy(reference: str, hypothesis: str) -> float:
    ref_words = _normalise(reference).split()
    hyp_words = _normalise(hypothesis).split()
    if not ref_words:
        return 1.0 if not hyp_words else 0.0
    matches = sum(1 for w in ref_words if w in hyp_words)
    return matches / len(ref_words)


def evaluate_ocr_page(
    reference_text: str,
    ocr_result: OCRPageResult,
) -> dict[str, Any]:
    """Score one OCR page result against the ground-truth text."""
    confidence = float(ocr_result.confidence) if ocr_result.confidence is not None else None
    return {
        "character_accuracy": round(character_accuracy(reference_text, ocr_result.text), 4),
        "word_accuracy": round(word_accuracy(reference_text, ocr_result.text), 4),
        "page_confidence": round(confidence, 4) if confidence is not None else None,
        "low_confidence": ocr_result.low_confidence,
    }
