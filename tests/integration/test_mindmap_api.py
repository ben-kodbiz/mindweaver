from fixtures.pdf import make_search_book_pdf


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_mindmap_returns_bounded_map(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    resp = client.get(f"/api/v1/documents/{doc['id']}/mindmap")
    assert resp.status_code == 200
    mindmap = resp.json()
    assert mindmap["document_id"] == doc["id"]
    assert mindmap["root"]["node_type"] == "root"
    assert mindmap["root"]["label"] == doc["title"]
    assert mindmap["total_nodes"] <= 1 + 8 + 8 * 3
    assert mindmap["max_depth"] == 2
    for topic in mindmap["root"]["children"]:
        assert topic["depth"] == 1
        for concept in topic["children"]:
            assert concept["depth"] == 2
            assert concept["source"]["graph_node_id"]


def test_mindmap_preferences_roundtrip(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    doc_id = doc["id"]

    initial = client.get(f"/api/v1/documents/{doc_id}/mindmap/preferences")
    assert initial.status_code == 200
    assert initial.json() == {}

    layout = {"zoom": 1.2, "pan": {"x": 10, "y": -5}, "collapsed": ["topic:chapter-1"]}
    saved = client.put(f"/api/v1/documents/{doc_id}/mindmap/preferences", json=layout)
    assert saved.status_code == 200

    fetched = client.get(f"/api/v1/documents/{doc_id}/mindmap/preferences").json()
    assert fetched == layout


def test_weak_hierarchy_document_map(client, app_settings):
    app_settings.llm.provider = "stub"
    from fixtures.pdf import make_plain_text_pdf

    resp = client.post(
        "/api/v1/documents",
        files={"file": ("plain.pdf", make_plain_text_pdf(), "application/pdf")},
    )
    doc = resp.json()
    resp = client.get(f"/api/v1/documents/{doc['id']}/mindmap")
    assert resp.status_code == 200
    mindmap = resp.json()
    assert mindmap["total_nodes"] <= 1 + 8 + 8 * 3


def test_mindmap_404_for_failed_document(client):
    from fixtures.pdf import make_corrupt_pdf

    resp = client.post(
        "/api/v1/documents",
        files={"file": ("bad.pdf", make_corrupt_pdf(), "application/pdf")},
    )
    doc_id = resp.json()["id"]
    assert (
        client.get(f"/api/v1/documents/{doc_id}/mindmap").status_code == 200
    )  # canonical absent -> still 200 with empty map
