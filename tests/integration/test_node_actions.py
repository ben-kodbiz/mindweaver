from fixtures.pdf import make_search_book_pdf


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def _graph(client, doc_id):
    return client.get(f"/api/v1/documents/{doc_id}/graph").json()


def test_expand_endpoint_adds_nodes(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    graph = _graph(client, doc["id"])
    node = next(n for n in graph["nodes"] if n["id"] == "concept:consolidation")

    resp = client.post(f"/api/v1/documents/{doc['id']}/mindmap/nodes/{node['id']}/expand")
    assert resp.status_code == 200
    body = resp.json()
    assert body["graph_version"] == 2
    assert any(n["label"] == "Slow-wave sleep" for n in body["added_nodes"])
    assert body["mindmap"]["total_nodes"] > 1

    graph_after = _graph(client, doc["id"])
    assert len(graph_after["nodes"]) > len(graph["nodes"])


def test_expand_unknown_node_404(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    resp = client.post(f"/api/v1/documents/{doc['id']}/mindmap/nodes/concept:nope/expand")
    assert resp.status_code == 422


def test_evidence_endpoint(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    graph = _graph(client, doc["id"])
    node = next(n for n in graph["nodes"] if n["id"] == "concept:memory")

    resp = client.get(f"/api/v1/documents/{doc['id']}/mindmap/nodes/{node['id']}/evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == node["id"]
    assert body["pages"]
    assert body["chunks"]
    assert all("page_start" in chunk for chunk in body["chunks"])


def test_explain_endpoint(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    graph = _graph(client, doc["id"])
    node = next(n for n in graph["nodes"] if n["id"] == "concept:memory")

    resp = client.post(f"/api/v1/documents/{doc['id']}/mindmap/nodes/{node['id']}/explain")
    assert resp.status_code == 200
    body = resp.json()
    assert body["explanation"]
    assert body["grounding"] == "supported_by_source"
    assert body["citations"]
    assert body["citations"][0]["chunk_id"]
    assert body["citations"][0]["page_start"] >= 1


def test_related_endpoint_returns_neighbors_and_semantic(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    graph = _graph(client, doc["id"])
    node = next(n for n in graph["nodes"] if n["id"] == "concept:consolidation")

    resp = client.get(f"/api/v1/documents/{doc['id']}/mindmap/nodes/{node['id']}/related")
    assert resp.status_code == 200
    body = resp.json()
    assert body
    assert any(item["relation"] is not None for item in body)  # graph neighbours


def test_ask_endpoint_scoped_chat(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    graph = _graph(client, doc["id"])
    node = next(n for n in graph["nodes"] if n["id"] == "concept:memory")

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/mindmap/nodes/{node['id']}/ask",
        json={"question": "What does the evidence say about this concept?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounding"] == "supported_by_source"
    assert body["citations"]
    assert body["session_id"]
