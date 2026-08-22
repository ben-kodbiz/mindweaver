"""Stage 14 unit tests: conflict detection and common concepts over graphs."""

from mindweaver.graph.types import GraphEdge, GraphNode, GraphNodeType, GraphRead
from mindweaver.notebooks import find_common_concepts, find_conflicts


def _node(node_id: str, label: str) -> GraphNode:
    return GraphNode(id=node_id, label=label, type=GraphNodeType.CONCEPT)


def _edge(source: str, target: str, relation: str) -> GraphEdge:
    return GraphEdge(source=source, target=target, relation=relation)


def _graph(edges: list[GraphEdge], nodes: list[GraphNode] | None = None) -> GraphRead:
    if nodes is None:
        ids = []
        for edge in edges:
            ids.extend([edge.source, edge.target])
        nodes = [_node(i, i.split(":")[-1]) for i in dict.fromkeys(ids)]
    return GraphRead(document_id="doc", version=1, nodes=nodes, edges=edges)


def test_no_conflicts_when_relations_agree():
    graphs = {
        "a": _graph([_edge("concept:x", "concept:y", "supports")]),
        "b": _graph([_edge("concept:x", "concept:y", "explains")]),
    }
    assert find_conflicts(graphs) == []


def test_conflict_when_supports_meets_contradicts():
    graphs = {
        "a": _graph([_edge("concept:x", "concept:y", "supports")]),
        "b": _graph([_edge("concept:y", "concept:x", "contradicts")]),
    }
    conflicts = find_conflicts(graphs)
    assert len(conflicts) == 1
    assert conflicts[0]["document_a"] == "a"
    assert conflicts[0]["document_b"] == "b"
    assert sorted(conflicts[0]["nodes"]) == ["concept:x", "concept:y"]
    assert {conflicts[0]["claim_a"], conflicts[0]["claim_b"]} == {
        "supports",
        "contradicts",
    }


def test_no_conflict_across_different_node_pairs():
    graphs = {
        "a": _graph([_edge("concept:x", "concept:y", "supports")]),
        "b": _graph([_edge("concept:y", "concept:z", "contradicts")]),
    }
    assert find_conflicts(graphs) == []


def test_common_concepts_requires_two_documents():
    graphs = {
        "a": _graph(
            [],
            nodes=[_node("concept:memory", "Memory"), _node("concept:sleep", "Sleep")],
        ),
        "b": _graph([], nodes=[_node("concept:memory", "Memory")]),
    }
    common = find_common_concepts(graphs)
    assert [item["node_id"] for item in common] == ["concept:memory"]
    assert len(common[0]["documents"]) == 2
