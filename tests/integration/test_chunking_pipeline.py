from fixtures.pdf import make_corrupt_pdf, make_structured_pdf


def _upload(client, content: bytes, filename: str = "book.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
    )


def test_upload_produces_chunks(client):
    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["status"] == "ready"

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks")
    assert chunks.status_code == 200
    body = chunks.json()
    assert body

    paragraph_texts = " ".join(c["text"] for c in body)
    assert "Memory is the faculty" in paragraph_texts

    section_chunk = next(c for c in body if c["section"] == "Section 1.1 The Problem")
    assert section_chunk["chapter"] == "Chapter 1: Foundations"
    assert section_chunk["section_path"] == [
        "Chapter 1: Foundations",
        "Section 1.1 The Problem",
    ]
    assert section_chunk["page_start"] >= 1
    assert section_chunk["page_end"] >= section_chunk["page_start"]
    assert section_chunk["token_count"] > 0


def test_chunks_have_contextual_headers(client):
    resp = _upload(client, make_structured_pdf())
    chunks = client.get(f"/api/v1/documents/{resp.json()['id']}/chunks").json()
    assert chunks
    for chunk in chunks:
        assert chunk["text"].startswith(chunk["section_path"][0]) if chunk["section_path"] else True


def test_reprocess_replaces_chunks(client):
    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    doc_id = resp.json()["id"]
    first = client.get(f"/api/v1/documents/{doc_id}/chunks").json()
    assert first

    client.post(f"/api/v1/documents/{doc_id}/reprocess")
    second = client.get(f"/api/v1/documents/{doc_id}/chunks").json()
    assert second
    assert {c["chunk_id"] for c in first} == {c["chunk_id"] for c in second}


def test_chunking_job_recorded(client):
    _upload(client, make_structured_pdf())
    jobs = client.get("/api/v1/jobs").json()
    assert any(job["job_type"] == "chunking" and job["status"] == "completed" for job in jobs)


def test_failed_document_has_no_chunks(client):
    resp = _upload(client, make_corrupt_pdf(), filename="bad.pdf")
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "failed"
    chunks = client.get(f"/api/v1/documents/{doc_id}/chunks").json()
    assert chunks == []


def test_delete_removes_chunks(client, app_settings):
    resp = _upload(client, make_structured_pdf())
    doc_id = resp.json()["id"]
    assert client.get(f"/api/v1/documents/{doc_id}/chunks").json()
    client.delete(f"/api/v1/documents/{doc_id}")
    # deleted document -> 404
    assert client.get(f"/api/v1/documents/{doc_id}/chunks").status_code == 404
