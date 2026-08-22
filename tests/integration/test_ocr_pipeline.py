from fixtures.pdf import (
    make_image_only_pdf,
    make_mixed_pdf,
    make_plain_text_pdf,
    make_scanned_pdf,
)


def _upload(client, content: bytes, filename: str = "doc.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
    )


def _ocr_available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        import rapidocr  # noqa: F401
    except ImportError:
        return False
    return True


def test_native_document_stays_ready(client):
    resp = _upload(client, make_plain_text_pdf(), filename="native.pdf")
    assert resp.status_code == 201
    assert resp.json()["status"] == "ready"


def test_scanned_document_becomes_ocr_required(client):
    resp = _upload(client, make_image_only_pdf(2), filename="scan.pdf")
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["status"] == "ocr_required"
    assert "OCR" in (doc["error_message"] or "")

    content = client.get(f"/api/v1/documents/{doc['id']}/content").json()
    assert len(content["pages"]) == 2
    assert content["pages"][0]["extraction_method"] == "ocr"
    assert content["pages"][0]["low_confidence"] is True
    assert not content["blocks"] or all(b["page_number"] >= 1 for b in content["blocks"])


def test_mixed_document_routes_pages(client):
    if not _ocr_available():
        import pytest

        pytest.skip("ocr extra not installed")
    resp = _upload(client, make_mixed_pdf(), filename="mixed.pdf")
    assert resp.status_code == 201
    doc = resp.json()
    content = client.get(f"/api/v1/documents/{doc['id']}/content").json()
    inspections = content["metadata"]["page_inspections"]
    assert inspections[0]["content_type"] in ("native", "mixed")
    assert inspections[1]["content_type"] == "scanned"


def test_reprocess_ocr_completes_scanned_document(client):
    if not _ocr_available():
        import pytest

        pytest.skip("ocr extra not installed")
    resp = _upload(client, make_scanned_pdf(), filename="scan.pdf")
    doc = resp.json()
    assert doc["status"] == "ocr_required"

    reprocessed = client.post(f"/api/v1/documents/{doc['id']}/reprocess-ocr")
    assert reprocessed.status_code == 200
    assert reprocessed.json()["status"] == "ready"

    content = client.get(f"/api/v1/documents/{doc['id']}/content").json()
    ocr_pages = [p for p in content["pages"] if p["extraction_method"] == "ocr"]
    assert ocr_pages
    assert all(p["confidence"] is not None for p in ocr_pages)

    all_text = " ".join(b["text"] for b in content["blocks"])
    assert "Scanned Document Title" in all_text or "scanned" in all_text.lower()

    jobs = client.get(f"/api/v1/documents/{doc['id']}/jobs").json()
    assert any(job["job_type"] == "ocr" and job["status"] == "completed" for job in jobs)


def test_reprocess_ocr_caches_results(client):
    if not _ocr_available():
        import pytest

        pytest.skip("ocr extra not installed")
    resp = _upload(client, make_scanned_pdf(), filename="scan.pdf")
    doc_id = resp.json()["id"]

    first = client.post(f"/api/v1/documents/{doc_id}/reprocess-ocr")
    assert first.json()["status"] == "ready"
    first_content = client.get(f"/api/v1/documents/{doc_id}/content").json()

    second = client.post(f"/api/v1/documents/{doc_id}/reprocess-ocr")
    assert second.json()["status"] == "ready"
    second_content = client.get(f"/api/v1/documents/{doc_id}/content").json()

    first_text = {b["text"] for b in first_content["blocks"]}
    second_text = {b["text"] for b in second_content["blocks"]}
    assert first_text == second_text
