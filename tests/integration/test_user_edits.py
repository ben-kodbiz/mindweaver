"""Stage 13: user notes and personal mind maps.

Source graph + user graph = personal view. Personal nodes/connections/notes
survive reprocessing; every mutation supports undo/redo; the personal view
can be exported.
"""

import json

from fixtures.pdf import make_search_book_pdf


def _upload(client, app_settings):
    app_settings.llm.provider = "stub"
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_add_personal_node(client, app_settings):
    doc = _upload(client, app_settings)
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "My own insight", "note": "This reminded me of something."},
    )
    assert resp.status_code == 200
    node = resp.json()
    assert node["id"] == "concept:my-own-insight"
    assert node["is_user_created"] is True
    assert node["note"] == "This reminded me of something."

    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert any(n["id"] == "concept:my-own-insight" for n in graph["nodes"])


def test_personal_node_survives_reprocessing(client, app_settings):
    doc = _upload(client, app_settings)
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "My own insight"},
    )

    # Regenerate the source graph (LLM extraction runs again).
    client.post(f"/api/v1/documents/{doc['id']}/graph/extract")

    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert "concept:my-own-insight" in ids  # survived
    assert "concept:memory" in ids  # source regenerated too


def test_note_on_source_node_survives_reprocessing(client, app_settings):
    doc = _upload(client, app_settings)
    updated = client.patch(
        f"/api/v1/documents/{doc['id']}/graph/nodes/concept:memory",
        json={"note": "Core concept of chapter one."},
    )
    assert updated.status_code == 200
    assert updated.json()["note"] == "Core concept of chapter one."

    client.post(f"/api/v1/documents/{doc['id']}/graph/extract")
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    memory = next(n for n in graph["nodes"] if n["id"] == "concept:memory")
    assert memory["note"] == "Core concept of chapter one."


def test_rename_update_flags_tags_color(client, app_settings):
    doc = _upload(client, app_settings)
    resp = client.patch(
        f"/api/v1/documents/{doc['id']}/graph/nodes/concept:memory",
        json={
            "label": "Human memory",
            "color": "#ffcc00",
            "tags": ["core", "chapter-1"],
            "is_important": True,
            "is_bookmarked": True,
        },
    ).json()
    assert resp["label"] == "Human memory"
    assert resp["color"] == "#ffcc00"
    assert resp["tags"] == ["core", "chapter-1"]
    assert resp["is_important"] is True
    assert resp["is_bookmarked"] is True


def test_create_and_remove_connection(client, app_settings):
    doc = _upload(client, app_settings)
    created = client.post(
        f"/api/v1/documents/{doc['id']}/graph/edges",
        json={
            "source": "concept:consolidation",
            "target": "concept:retrieval-cues",
            "relation": "supports",
            "note": "user hypothesis",
        },
    )
    assert created.status_code == 200
    edge = created.json()
    assert edge["relation"] == "supports"

    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    triples = {(e["source"], e["target"], e["relation"]) for e in graph["edges"]}
    assert (
        "concept:consolidation",
        "concept:retrieval-cues",
        "supports",
    ) in triples

    removed = client.request(
        "DELETE",
        f"/api/v1/documents/{doc['id']}/graph/edges",
        json={
            "source": "concept:consolidation",
            "target": "concept:retrieval-cues",
            "relation": "supports",
        },
    )
    assert removed.status_code == 204
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    triples = {(e["source"], e["target"], e["relation"]) for e in graph["edges"]}
    assert (
        "concept:consolidation",
        "concept:retrieval-cues",
        "supports",
    ) not in triples


def test_duplicate_connection_conflict(client, app_settings):
    doc = _upload(client, app_settings)
    payload = {
        "source": "concept:consolidation",
        "target": "concept:memory",
        "relation": "affects",  # already extracted by the stub
    }
    resp = client.post(f"/api/v1/documents/{doc['id']}/graph/edges", json=payload)
    assert resp.status_code == 409


def test_merge_nodes(client, app_settings):
    doc = _upload(client, app_settings)
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "Recall", "tags": ["personal"]},
    )

    merged = client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes/concept:recall/merge",
        json={"into": "concept:retrieval-cues"},
    )
    assert merged.status_code == 200
    body = merged.json()
    assert body["id"] == "concept:retrieval-cues"
    assert "personal" in body["tags"]

    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert "concept:recall" not in ids
    assert "concept:retrieval-cues" in ids
    # no dangling edges to the removed node
    assert all(e["source"] != "concept:recall" for e in graph["edges"])
    assert all(e["target"] != "concept:recall" for e in graph["edges"])


def test_undo_redo_roundtrip(client, app_settings):
    doc = _upload(client, app_settings)
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "Undo me"},
    )
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert "concept:undo-me" in {n["id"] for n in graph["nodes"]}

    undone = client.post(f"/api/v1/documents/{doc['id']}/graph/undo")
    assert undone.status_code == 200
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert "concept:undo-me" not in {n["id"] for n in graph["nodes"]}
    # source layer untouched by undo
    assert "concept:memory" in {n["id"] for n in graph["nodes"]}

    redone = client.post(f"/api/v1/documents/{doc['id']}/graph/redo")
    assert redone.status_code == 200
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert "concept:undo-me" in {n["id"] for n in graph["nodes"]}


def test_undo_exhaustion_returns_409(client, app_settings):
    doc = _upload(client, app_settings)
    resp = client.post(f"/api/v1/documents/{doc['id']}/graph/undo")
    assert resp.status_code == 409
    assert "nothing to undo" in resp.json()["error"]["message"]

    redo = client.post(f"/api/v1/documents/{doc['id']}/graph/redo")
    assert redo.status_code == 409


def test_export_works(client, app_settings):
    doc = _upload(client, app_settings)
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "Exported insight", "note": "kept"},
    )

    resp = client.get(f"/api/v1/documents/{doc['id']}/graph/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-type"].lower() or (
        resp.headers.get("content-disposition", "").startswith("attachment")
    )
    data = json.loads(resp.content)
    assert data["document_id"] == doc["id"]
    labels = {n["label"] for n in data["nodes"]}
    assert "Exported insight" in labels
    assert "Memory" in labels  # source layer exported alongside


def test_user_edge_survives_reprocessing(client, app_settings):
    doc = _upload(client, app_settings)
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/nodes",
        json={"label": "Working memory"},
    )
    client.post(
        f"/api/v1/documents/{doc['id']}/graph/edges",
        json={
            "source": "concept:working-memory",
            "target": "concept:memory",
            "relation": "part_of",
        },
    )

    client.post(f"/api/v1/documents/{doc['id']}/graph/extract")
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    triples = {(e["source"], e["target"], e["relation"]) for e in graph["edges"]}
    assert ("concept:working-memory", "concept:memory", "part_of") in triples


def test_delete_node(client, app_settings):
    doc = _upload(client, app_settings)
    deleted = client.delete(f"/api/v1/documents/{doc['id']}/graph/nodes/concept:retrieval-cues")
    assert deleted.status_code == 204
    graph = client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert "concept:retrieval-cues" not in {n["id"] for n in graph["nodes"]}
    # edges touching the deleted node are gone too
    assert all("concept:retrieval-cues" not in (e["source"], e["target"]) for e in graph["edges"])
