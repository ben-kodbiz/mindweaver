"""Stage 12: graph exploration — filtering, capping, and neighbourhood focus."""

import pytest
from fixtures.pdf import make_search_book_pdf


@pytest.fixture
def doc_id(client, app_settings):
    app_settings.llm.provider = "stub"
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_node_type_filter(client, doc_id):
    resp = client.get(f"/api/v1/documents/{doc_id}/graph", params={"node_types": ["concept"]})
    assert resp.status_code == 200
    body = resp.json()
    assert {n["type"] for n in body["nodes"]} == {"concept"}
    # person:researchers is filtered out together with its (absent) edges
    assert all(node["id"] != "person:researchers" for node in body["nodes"])
    assert all(edge["source"] != "person:researchers" for edge in body["edges"])


def test_relation_filter(client, doc_id):
    graph = client.get(f"/api/v1/documents/{doc_id}/graph").json()
    assert any(edge["relation"] == "affects" for edge in graph["edges"])

    resp = client.get(f"/api/v1/documents/{doc_id}/graph", params={"relations": ["part_of"]})
    body = resp.json()
    assert body["edges"] == []
    # nodes are still returned so the view can render them
    assert body["nodes"]

    affects_only = client.get(
        f"/api/v1/documents/{doc_id}/graph", params={"relations": ["affects"]}
    ).json()
    assert {edge["relation"] for edge in affects_only["edges"]} == {"affects"}
    # edges referencing filtered-out nodes must be dropped
    node_ids = {node["id"] for node in affects_only["nodes"]}
    assert all(edge["source"] in node_ids for edge in affects_only["edges"])
    assert all(edge["target"] in node_ids for edge in affects_only["edges"])


def test_focus_neighborhood(client, doc_id):
    resp = client.get(
        f"/api/v1/documents/{doc_id}/graph",
        params={"focus_node_id": "concept:memory"},
    )
    body = resp.json()
    ids = {node["id"] for node in body["nodes"]}
    # memory plus its 1-hop neighbours (consolidation, retrieval cues)
    assert ids == {"concept:memory", "concept:consolidation", "concept:retrieval-cues"}
    assert all(edge["source"] in ids and edge["target"] in ids for edge in body["edges"])


def test_focus_unknown_node_returns_empty_graph(client, doc_id):
    resp = client.get(
        f"/api/v1/documents/{doc_id}/graph",
        params={"focus_node_id": "concept:nope"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []


def test_limit_caps_by_degree(client, doc_id):
    full = client.get(f"/api/v1/documents/{doc_id}/graph").json()
    degree = {}
    for edge in full["edges"]:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    best = sorted(degree, key=lambda n: degree[n], reverse=True)[:2]

    capped = client.get(f"/api/v1/documents/{doc_id}/graph", params={"limit": 2}).json()
    assert len(capped["nodes"]) == 2
    assert {node["id"] for node in capped["nodes"]} == set(best)
    # edges must only connect kept nodes
    kept = {node["id"] for node in capped["nodes"]}
    assert all(edge["source"] in kept and edge["target"] in kept for edge in capped["edges"])


def test_limit_never_orphans_edges(client, doc_id):
    """With limit >= node count nothing changes; below that every remaining
    edge still connects two rendered nodes."""
    full = client.get(f"/api/v1/documents/{doc_id}/graph").json()
    total = len(full["nodes"])
    for cap in range(1, total + 1):
        capped = client.get(f"/api/v1/documents/{doc_id}/graph", params={"limit": cap}).json()
        assert len(capped["nodes"]) == cap
        kept = {node["id"] for node in capped["nodes"]}
        assert all(edge["source"] in kept and edge["target"] in kept for edge in capped["edges"])


def test_combined_filters(client, doc_id):
    resp = client.get(
        f"/api/v1/documents/{doc_id}/graph",
        params={"node_types": ["concept"], "focus_node_id": "concept:memory"},
    )
    body = resp.json()
    assert {n["type"] for n in body["nodes"]} <= {"concept"}
    assert "concept:memory" in {n["id"] for n in body["nodes"]}
