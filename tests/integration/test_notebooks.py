"""Stage 14 integration tests: notebooks, cross-document retrieval and graphs."""

from fixtures.pdf import make_pdf, make_search_book_pdf


def _upload(client, content: bytes, filename: str):
    resp = client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def _notebook(client, app_settings, *documents) -> dict:
    app_settings.llm.provider = "stub"
    created = client.post(
        "/api/v1/notebooks",
        json={"title": "Memory studies", "description": "cross-book"},
    )
    assert created.status_code == 201
    notebook = created.json()
    for doc in documents:
        added = client.post(
            f"/api/v1/notebooks/{notebook['id']}/documents",
            json={"document_id": doc["id"]},
        )
        assert added.status_code == 201
    return notebook


def test_notebook_crud(client, app_settings):
    app_settings.llm.provider = "stub"
    created = client.post("/api/v1/notebooks", json={"title": "Test notebook"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]

    listing = client.get("/api/v1/notebooks").json()
    assert any(n["id"] == notebook_id for n in listing)
    assert all("document_count" in n for n in listing)

    detail = client.get(f"/api/v1/notebooks/{notebook_id}")
    assert detail.status_code == 200
    assert detail.json()["documents"] == []

    deleted = client.delete(f"/api/v1/notebooks/{notebook_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/notebooks/{notebook_id}").status_code == 404


def test_notebook_membership_rules(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client, make_search_book_pdf(), "a.pdf")
    notebook = _notebook(client, app_settings)

    # unknown document
    missing = client.post(
        f"/api/v1/notebooks/{notebook['id']}/documents",
        json={"document_id": "does-not-exist"},
    )
    assert missing.status_code == 409

    added = client.post(
        f"/api/v1/notebooks/{notebook['id']}/documents",
        json={"document_id": doc["id"]},
    )
    assert added.status_code == 201

    duplicate = client.post(
        f"/api/v1/notebooks/{notebook['id']}/documents",
        json={"document_id": doc["id"]},
    )
    assert duplicate.status_code == 409

    removed = client.delete(f"/api/v1/notebooks/{notebook['id']}/documents/{doc['id']}")
    assert removed.status_code == 204


def test_cross_document_retrieval_with_source_labels(client, app_settings):
    app_settings.llm.provider = "stub"
    doc_a = _upload(client, make_search_book_pdf(), "book_a.pdf")
    doc_b = _upload(client, make_search_book_pdf(), "book_b.pdf")
    _upload(client, make_pdf(5), "outsider.pdf")  # not in the notebook
    notebook = _notebook(client, app_settings, doc_a, doc_b)

    resp = client.get(
        f"/api/v1/notebooks/{notebook['id']}/search",
        params={"q": "memory is the faculty information encoded"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2

    hit_docs = {hit["document_id"] for hit in body["results"]}
    assert hit_docs == {doc_a["id"], doc_b["id"]}  # both books, no outsider

    for hit in body["results"]:
        expected = doc_a["title"] if hit["document_id"] == doc_a["id"] else doc_b["title"]
        assert hit["source_label"] == expected  # source labels attached


def test_same_concept_across_books_merges_in_graph(client, app_settings):
    app_settings.llm.provider = "stub"
    doc_a = _upload(client, make_search_book_pdf(), "book_a.pdf")
    doc_b = _upload(client, make_search_book_pdf(), "book_b.pdf")
    notebook = _notebook(client, app_settings, doc_a, doc_b)

    graph = client.get(f"/api/v1/notebooks/{notebook['id']}/graph").json()
    memory = next(node for node in graph["nodes"] if node["id"] == "concept:memory")
    # one merged node carrying BOTH source documents (tracked by id)
    assert len(memory["documents"]) == 2
    assert len(memory["source_chunks"]) >= 2

    consolidation = next(node for node in graph["nodes"] if node["id"] == "concept:consolidation")
    assert len(consolidation["documents"]) == 2
    # titles exposed for labelling even when identical
    assert len(set(graph["document_titles"])) == 2


def test_compare_documents_reports_common_and_conflicts(client, app_settings):
    app_settings.llm.provider = "stub"
    doc_a = _upload(client, make_search_book_pdf(), "book_a.pdf")
    doc_b = _upload(client, make_search_book_pdf(), "book_b.pdf")
    notebook = _notebook(client, app_settings, doc_a, doc_b)

    # Book B claims the opposite of book A over the same concept pair.
    conflict_edge = client.post(
        f"/api/v1/documents/{doc_b['id']}/graph/edges",
        json={
            "source": "concept:consolidation",
            "target": "concept:memory",
            "relation": "contradicts",
            "note": "counter-claim",
        },
    )
    assert conflict_edge.status_code == 200

    report = client.get(f"/api/v1/notebooks/{notebook['id']}/compare").json()
    assert report["document_count"] == 2

    common_ids = {item["node_id"] for item in report["common_concepts"]}
    assert {"concept:memory", "concept:consolidation"} <= common_ids

    assert report["conflicts"]
    conflict = report["conflicts"][0]
    assert {conflict["claim_a"], conflict["claim_b"]} == {"affects", "contradicts"}
    assert conflict["document_a"] != conflict["document_b"]

    uniques = report["unique_by_document"]
    assert doc_a["id"] in uniques and doc_b["id"] in uniques


def test_large_combined_corpus_still_works(client, app_settings):
    app_settings.llm.provider = "stub"
    doc_a = _upload(client, make_search_book_pdf(), "book_a.pdf")
    doc_big = _upload(client, make_pdf(num_pages=100), "big.pdf")
    notebook = _notebook(client, app_settings, doc_a, doc_big)

    resp = client.get(
        f"/api/v1/notebooks/{notebook['id']}/search",
        params={"q": "consolidation stabilises memories"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    graph = client.get(f"/api/v1/notebooks/{notebook['id']}/graph").json()
    assert graph["nodes"]  # merged graph still renders within bounds
