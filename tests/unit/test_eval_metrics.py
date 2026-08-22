"""Stage 21: evaluation framework tests."""

from mindweaver.evaluation import (
    GraphQualityReport,
    character_accuracy,
    evaluate_graph,
    evaluate_ocr_page,
    word_accuracy,
)
from mindweaver.graph.types import GraphEdge, GraphNode, GraphNodeType, GraphRead
from mindweaver.ocr.base import OCRPageResult


def _node(node_id: str, label: str) -> GraphNode:
    return GraphNode(id=node_id, label=label, type=GraphNodeType.CONCEPT)


def test_clean_graph_scores_high():
    graph = GraphRead(
        document_id="d",
        version=1,
        nodes=[
            GraphNode(
                id="concept:memory",
                label="Memory",
                type=GraphNodeType.CONCEPT,
                source_chunks=["c1"],
            ),
            GraphNode(
                id="concept:sleep",
                label="Sleep",
                type=GraphNodeType.CONCEPT,
                source_chunks=["c2"],
            ),
        ],
        edges=[
            GraphEdge(
                source="concept:sleep",
                target="concept:memory",
                relation="affects",
                source_chunks=["c1"],
            )
        ],
    )
    report = evaluate_graph(graph)
    assert isinstance(report, GraphQualityReport)
    assert report.duplicate_nodes == 0
    assert report.invalid_relationships == 0
    assert report.orphan_nodes == 0
    assert report.source_coverage == 1.0


def test_duplicate_labels_detected():
    graph = GraphRead(
        document_id="d",
        version=1,
        nodes=[_node("concept:a", "Memory"), _node("concept:b", "memory ")],
        edges=[],
    )
    report = evaluate_graph(graph)
    assert report.duplicate_nodes >= 1
    assert report.issues


def test_unattributed_edge_is_invalid():
    graph = GraphRead(
        document_id="d",
        version=1,
        nodes=[
            _node("concept:x", "X"),
            _node("concept:y", "Y"),
        ],
        edges=[GraphEdge(source="concept:x", target="concept:y", relation="affects")],
    )
    report = evaluate_graph(graph)
    assert report.invalid_relationships == 1


def test_self_loop_is_invalid():
    graph = GraphRead(
        document_id="d",
        version=1,
        nodes=[_node("concept:x", "X")],
        edges=[GraphEdge(source="concept:x", target="concept:x", relation="affects")],
    )
    report = evaluate_graph(graph)
    assert report.invalid_relationships >= 1
    assert report.orphan_nodes == 0  # self loop counts as connected


def test_character_and_word_accuracy():
    reference = "Memory is the faculty by which information is encoded."
    perfect = evaluate_ocr_page(
        reference,
        OCRPageResult(page_number=1, text=reference, confidence=0.99),
    )
    assert perfect["character_accuracy"] > 0.99
    assert perfect["word_accuracy"] == 1.0

    noisy = evaluate_ocr_page(
        reference,
        OCRPageResult(
            page_number=1,
            text="Mem0ry is the facuity by which inf0 is encoded.",
            confidence=0.6,
        ),
    )
    assert 0.5 < noisy["character_accuracy"] < 0.99
    assert noisy["page_confidence"] == 0.6

    garbage = evaluate_ocr_page(
        reference, OCRPageResult(page_number=1, text="", confidence=None, low_confidence=True)
    )
    assert garbage["character_accuracy"] < 0.2
    assert garbage["low_confidence"] is True


def test_word_accuracy_partial():
    ref = "the quick brown fox"
    hyp = "the brown fox jumps"
    # 3 of 4 reference words appear in hypothesis
    assert word_accuracy(ref, hyp) == 0.75
    assert 0 < character_accuracy(ref, hyp) <= 1
