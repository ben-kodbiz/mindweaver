from fixtures.pdf import make_corrupt_pdf, make_structured_pdf
from mindweaver.config import DocumentProcessorConfig, Settings


def _upload(client, content: bytes, filename: str = "book.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
    )


def test_upload_extracts_and_exposes_content(client, app_settings):
    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["status"] == "ready"
    assert doc["page_count"] >= 1

    content_resp = client.get(f"/api/v1/documents/{doc['id']}/content")
    assert content_resp.status_code == 200
    content = content_resp.json()
    assert content["document_id"] == doc["id"]
    assert content["processor"] == "pypdf"
    assert content["pages"]
    assert content["blocks"]

    canonical_path = app_settings.storage.derived_dir / doc["id"] / "canonical.json"
    assert canonical_path.exists()


def test_content_acceptance_paragraph_traceability(client):
    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    doc = resp.json()
    content = client.get(f"/api/v1/documents/{doc['id']}/content").json()

    paragraph = next(b for b in content["blocks"] if b["text"].startswith("Memory is the faculty"))
    assert paragraph["page_number"] >= 1
    assert paragraph["section_path"] == [
        "Chapter 1: Foundations",
        "Section 1.1 The Problem",
    ]


def test_document_jobs_include_extraction(client):
    _upload(client, make_structured_pdf())
    jobs = client.get("/api/v1/jobs").json()
    job_types = [job["job_type"] for job in jobs]
    assert "metadata_extraction" in job_types
    assert "document_extraction" in job_types


def test_extraction_failure_marks_document_failed(client):
    resp = _upload(client, make_corrupt_pdf(), filename="bad.pdf")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error_message"]

    content_resp = client.get(f"/api/v1/documents/{body['id']}/content")
    assert content_resp.status_code == 404


def test_content_not_available_for_failed_document(client):
    resp = _upload(client, make_corrupt_pdf())
    doc_id = resp.json()["id"]
    content_resp = client.get(f"/api/v1/documents/{doc_id}/content")
    assert content_resp.status_code == 404
    assert content_resp.json()["error"]["code"] == "http_error"


def test_delete_removes_derived_content(client, app_settings):
    resp = _upload(client, make_structured_pdf())
    doc_id = resp.json()["id"]
    derived = app_settings.storage.derived_dir / doc_id
    assert derived.exists()
    client.delete(f"/api/v1/documents/{doc_id}")
    assert not derived.exists()


def test_reprocess_regenerates_content(client):
    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    doc_id = resp.json()["id"]
    first = client.get(f"/api/v1/documents/{doc_id}/content").json()
    assert first["blocks"]

    reprocessed = client.post(f"/api/v1/documents/{doc_id}/reprocess")
    assert reprocessed.status_code == 200
    second = client.get(f"/api/v1/documents/{doc_id}/content").json()
    assert second["document_id"] == doc_id
    assert len(second["blocks"]) == len(first["blocks"])


def test_docling_processor_end_to_end(client, app_settings):
    settings = app_settings
    if settings.document_processor.backend == "pypdf":
        client.app.state.settings = Settings(
            app=settings.app,
            database=settings.database,
            storage=settings.storage,
            security=settings.security,
            document_processor=DocumentProcessorConfig(backend="docling"),
        )
    try:
        import docling  # noqa: F401
    except ImportError:
        client.app.state.settings = settings
        import pytest

        pytest.skip("docling extra not installed")

    resp = _upload(client, make_structured_pdf(), filename="book.pdf")
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["status"] == "ready"

    content = client.get(f"/api/v1/documents/{doc['id']}/content").json()
    assert content["processor"] == "docling"

    paragraphs = [b for b in content["blocks"] if b["block_type"] == "paragraph"]
    assert paragraphs

    by_text = {b["text"] for b in content["blocks"]}
    assert any("Memory is the faculty" in t for t in by_text)

    tables = [b for b in content["blocks"] if b["block_type"] == "table"]
    assert tables, "docling should detect the fixture table"
    assert any("Group" in "".join(row) for row in tables[0]["table_rows"])

    figures = [b for b in content["blocks"] if b["block_type"] == "figure"]
    assert figures, "docling should detect the fixture image"
