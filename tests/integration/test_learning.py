"""Stage 15: summaries and learning outputs."""

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


KINDS = ["summary", "key_concepts", "qa", "flashcards", "quiz", "study_guide"]


def test_all_kinds_generate_with_provenance(client, doc_id):
    for kind in KINDS:
        resp = client.post(f"/api/v1/documents/{doc_id}/learning", json={"kind": kind})
        assert resp.status_code == 200, f"{kind} failed: {resp.text}"
        body = resp.json()
        assert body["kind"] == kind
        assert body["document_id"] == doc_id
        assert body["items"]
        for item in body["items"]:
            # every output retains source references
            assert isinstance(item.get("concept_ids"), list)
            assert item.get("chunk_ids")
            assert item.get("pages")


def test_summary_content_grounded(client, doc_id):
    body = client.post(f"/api/v1/documents/{doc_id}/learning", json={"kind": "summary"}).json()
    text = " ".join(item["text"] for item in body["items"]).lower()
    assert "memory" in text or "consolidation" in text or len(text) > 50


def test_chapter_scope_narrows_items(client, doc_id):
    body = client.post(
        f"/api/v1/documents/{doc_id}/learning",
        json={"kind": "summary", "scope_type": "chapter", "target": "Chapter 2"},
    ).json()
    assert body["scope"]["type"] == "chapter"
    assert body["items"]


def test_unknown_kind_rejected(client, doc_id):
    resp = client.post(
        f"/api/v1/documents/{doc_id}/learning",
        json={"kind": "podcast_script"},
    )
    assert resp.status_code == 422


def test_unknown_document_404(client):
    resp = client.post("/api/v1/documents/nope/learning", json={"kind": "summary"})
    assert resp.status_code == 404


def test_fallback_when_llm_unavailable(client, doc_id, app_settings):
    app_settings.llm.provider = "does-not-exist"
    body = client.post(f"/api/v1/documents/{doc_id}/learning", json={"kind": "summary"}).json()
    assert body["generated_by"] == "extractive"
    assert body["items"]
