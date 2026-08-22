from fixtures.pdf import (
    make_corrupt_pdf,
    make_empty_pdf,
    make_password_protected_pdf,
    make_pdf,
)


def _upload(client, content: bytes, filename: str = "book.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
    )


def test_upload_small_native_pdf(client):
    resp = _upload(client, make_pdf(num_pages=3), filename="book.pdf")
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "book"
    assert body["original_filename"] == "book.pdf"
    assert body["page_count"] == 3
    assert body["status"] == "ready"
    assert body["file_size"] > 0
    assert len(body["sha256"]) == 64


def test_upload_large_native_pdf(client):
    resp = _upload(client, make_pdf(num_pages=100), filename="big.pdf")
    assert resp.status_code == 201
    assert resp.json()["page_count"] == 100
    assert resp.json()["status"] == "ready"


def test_upload_empty_pdf_is_rejected(client):
    resp = _upload(client, make_empty_pdf())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "http_error"


def test_upload_non_pdf_is_rejected(client):
    resp = _upload(client, b"not a pdf at all", filename="book.txt")
    assert resp.status_code == 400


def test_upload_corrupt_pdf_is_stored_but_failed(client):
    resp = _upload(client, make_corrupt_pdf())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error_message"]
    assert body["page_count"] is None


def test_upload_password_protected_pdf_is_failed(client):
    resp = _upload(client, make_password_protected_pdf())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert "password" in body["error_message"]


def test_duplicate_upload_is_rejected(client):
    content = make_pdf(num_pages=2)
    first = _upload(client, content)
    assert first.status_code == 201
    second = _upload(client, content, filename="copy.pdf")
    assert second.status_code == 409
    assert second.json()["error"]["request_id"] == second.headers["X-Request-ID"]


def test_list_documents(client):
    _upload(client, make_pdf(num_pages=2), filename="a.pdf")
    _upload(client, make_pdf(num_pages=5), filename="b.pdf")
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_get_document(client):
    created = _upload(client, make_pdf(num_pages=4)).json()
    resp = client.get(f"/api/v1/documents/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_missing_document_404(client):
    resp = client.get("/api/v1/documents/does-not-exist")
    assert resp.status_code == 404


def test_delete_document_removes_file(client, app_settings):
    created = _upload(client, make_pdf(num_pages=2)).json()
    document_id = created["id"]

    original_dir = app_settings.storage.originals_dir
    files_before = {p.name for p in original_dir.iterdir()}
    assert any(document_id in name for name in files_before)

    resp = client.delete(f"/api/v1/documents/{document_id}")
    assert resp.status_code == 204

    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    files_after = {p.name for p in original_dir.iterdir()}
    assert not any(document_id in name for name in files_after)


def test_reprocess_document(client):
    created = _upload(client, make_pdf(num_pages=3)).json()
    document_id = created["id"]

    jobs_resp = client.get(f"/api/v1/documents/{document_id}/jobs")
    assert jobs_resp.status_code == 200
    assert len(jobs_resp.json()) == 4
    assert all(job["status"] == "completed" for job in jobs_resp.json())

    resp = client.post(f"/api/v1/documents/{document_id}/reprocess")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    jobs_resp = client.get(f"/api/v1/documents/{document_id}/jobs")
    assert len(jobs_resp.json()) == 8


def test_reprocess_corrupt_pdf_fails_cleanly(client):
    created = _upload(client, make_corrupt_pdf()).json()
    resp = client.post(f"/api/v1/documents/{created['id']}/reprocess")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


def test_download_original(client):
    content = make_pdf(num_pages=2)
    created = _upload(client, content, filename="orig.pdf").json()
    resp = client.get(f"/api/v1/documents/{created['id']}/file")
    assert resp.status_code == 200
    assert resp.content == content
    assert resp.headers["content-type"] == "application/pdf"


def test_jobs_listing(client):
    _upload(client, make_pdf(num_pages=2), filename="a.pdf")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 4
    assert {job["job_type"] for job in jobs} == {
        "metadata_extraction",
        "document_extraction",
        "chunking",
        "graph_extraction",
    }
    assert all(job["status"] == "completed" for job in jobs)


def test_get_job(client):
    _upload(client, make_pdf(num_pages=2))
    jobs = client.get("/api/v1/jobs").json()
    job_id = jobs[0]["id"]
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


def test_acceptance_upload_to_completed(client, app_settings):
    resp = _upload(client, make_pdf(num_pages=5), filename="manual.pdf")
    assert resp.status_code == 201
    doc = resp.json()

    listing = client.get("/api/v1/documents").json()
    assert any(item["id"] == doc["id"] for item in listing["items"])
    assert doc["status"] == "ready"

    downloaded = client.get(f"/api/v1/documents/{doc['id']}/file")
    assert downloaded.status_code == 200

    deleted = client.delete(f"/api/v1/documents/{doc['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{doc['id']}").status_code == 404
    original_dir = app_settings.storage.originals_dir
    assert not any(doc["id"] in p.name for p in original_dir.iterdir())
