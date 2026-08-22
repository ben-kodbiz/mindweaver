from fixtures.pdf import make_search_book_pdf


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_upload_produces_graph(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    assert doc["status"] == "ready"

    resp = client.get(f"/api/v1/documents/{doc['id']}/graph")
    assert resp.status_code == 200
    graph = resp.json()
    assert graph["document_id"] == doc["id"]
    assert graph["version"] >= 1
    assert graph["nodes"]
    assert graph["edges"]
    # at least some nodes retain source evidence
    assert any(n["source_chunks"] for n in graph["nodes"])
    # every edge is traceable to evidence or marked as inference
    for edge in graph["edges"]:
        assert edge["source_chunks"] or edge["is_inference"]


def test_graph_job_recorded(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    jobs = client.get(f"/api/v1/documents/{doc['id']}/jobs").json()
    assert any(
        job["job_type"] == "graph_extraction" and job["status"] == "completed" for job in jobs
    )


def test_reextract_increments_version(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    first = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert first["version"] == 1

    second = client.post(f"/api/v1/documents/{doc['id']}/graph/extract")
    assert second.status_code == 200
    assert second.json()["version"] == 2


def test_graph_not_available_for_failed_document(client):
    from fixtures.pdf import make_corrupt_pdf

    resp = client.post(
        "/api/v1/documents",
        files={"file": ("bad.pdf", make_corrupt_pdf(), "application/pdf")},
    )
    doc_id = resp.json()["id"]
    assert client.get(f"/api/v1/documents/{doc_id}/graph").status_code == 404


def test_graph_extraction_failure_is_non_fatal(client, app_settings):
    app_settings.llm.provider = "stub"
    doc = _upload(client)
    doc_id = doc["id"]

    from mindweaver.graph import extractor as extractor_module
    from mindweaver.llm.stub import StubLLMProvider

    class BrokenStub(StubLLMProvider):
        def complete(self, messages, **kwargs):
            raise RuntimeError("llm down")

    original = extractor_module.get_llm_provider
    extractor_module.get_llm_provider = lambda settings: BrokenStub()  # type: ignore[assignment]
    try:
        client.post(f"/api/v1/documents/{doc_id}/graph/extract")
    finally:
        extractor_module.get_llm_provider = original

    # document itself stays usable
    assert client.get(f"/api/v1/documents/{doc_id}").json()["status"] == "ready"
    jobs = client.get(f"/api/v1/documents/{doc_id}/jobs").json()
    assert any(job["job_type"] == "graph_extraction" and job["status"] == "failed" for job in jobs)
