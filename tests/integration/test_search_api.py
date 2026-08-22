from fixtures.pdf import make_search_book_pdf


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_search_returns_evidence(client):
    doc = _upload(client)

    resp = client.get("/api/v1/search", params={"q": "memory is the faculty information encoded"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    hit = body["results"][0]
    assert hit["document_id"] == doc["id"]
    assert hit["page_start"] >= 1
    assert hit["section"] == "Section 1.1 The Problem"
    assert hit["section_path"] == ["Chapter 1: Foundations", "Section 1.1 The Problem"]
    assert hit["chunk_id"]
    assert "retrieval_score" in hit
    assert "rerank_score" in hit


def test_search_negative_query(client):
    _upload(client)
    resp = client.get("/api/v1/search", params={"q": "whales photosynthesise underwater"})
    assert resp.json()["total"] == 0


def test_search_document_filter(client):
    _upload(client)
    resp = client.get(
        "/api/v1/search", params={"q": "consolidation", "document_id": "does-not-exist"}
    )
    assert resp.json()["total"] == 0


def test_search_requires_query(client):
    resp = client.get("/api/v1/search")
    assert resp.status_code == 422


def test_search_semantic_question(client):
    doc = _upload(client)
    resp = client.get("/api/v1/search", params={"q": "How are memories stabilised over time?"})
    top = resp.json()["results"][0]
    assert top["document_id"] == doc["id"]
    assert top["section"] == "Section 2.1 Consolidation"
