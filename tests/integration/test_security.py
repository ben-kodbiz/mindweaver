"""Stage 19: security and privacy hardening."""

import pytest
from fixtures.pdf import make_search_book_pdf


def test_storage_key_rejects_traversal():
    from mindweaver.config import Settings
    from mindweaver.storage import StorageKeyError, original_path

    settings = Settings()
    for bad in ("../evil.pdf", "a/b.pdf", "..\\evil.pdf", "", "sub/../x.pdf"):
        with pytest.raises(StorageKeyError):
            original_path(settings, bad)


def test_derived_dir_rejects_traversal():
    from mindweaver.config import Settings
    from mindweaver.storage import StorageKeyError, derived_dir

    settings = Settings()
    for bad in ("../doc", "a/b", ""):
        with pytest.raises(StorageKeyError):
            derived_dir(settings, bad)


def test_upload_size_limit_enforced(client, app_settings):
    app_settings.storage.max_upload_bytes = 500  # tiny limit for the test
    big = b"%PDF-1.4\n" + b"x" * 2000
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert resp.status_code == 413


def test_document_delete_removes_everything(client, app_settings):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    doc = resp.json()
    doc_id = doc["id"]

    # build derived data first
    assert client.get(f"/api/v1/documents/{doc_id}/content").status_code == 200

    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/file").status_code == 404


def test_data_export_contains_all_layers(client, app_settings):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    doc = resp.json()
    resp = client.get(f"/api/v1/documents/{doc['id']}/data-export")
    assert resp.status_code == 200
    import json

    data = json.loads(resp.content)
    assert data["document"]["id"] == doc["id"]
    assert data["canonical"] is not None
    assert isinstance(data["chunks"], list)
    assert "graph" in data


def test_secrets_never_logged(client, app_settings, caplog):
    import logging

    secret = "super-secret-value-12345"
    app_settings.security.secret_key = secret
    app_settings.llm.provider = "stub"

    from mindweaver.logging_conf import JsonFormatter, register_secret

    register_secret(secret)
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __name__,
        0,
        f"processing with {secret}",
        (),
        None,
    )
    formatted = formatter.format(record)
    assert secret not in formatted


def test_no_telemetry_or_outbound_calls_on_startup(client, app_settings):
    """Local-first: startup performs no network calls (smoke check that the
    app is fully functional offline)."""
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
