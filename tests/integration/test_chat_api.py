from fixtures.pdf import make_search_book_pdf


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_create_and_get_session(client, app_settings):
    _upload(client)
    created = client.post("/api/v1/chat/sessions", json={})
    assert created.status_code == 201
    session_id = created.json()["id"]

    detail = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == session_id
    assert detail.json()["messages"] == []


def test_document_scoped_session(client, app_settings):
    doc = _upload(client)
    created = client.post("/api/v1/chat/sessions", json={"document_id": doc["id"]}).json()
    assert created["document_id"] == doc["id"]


def test_ask_returns_grounded_answer_with_citations(client, app_settings):
    doc = _upload(client)
    app_settings.llm.provider = "stub"
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]

    resp = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "What is the faculty by which information is encoded?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounding"] == "supported_by_source"
    assert body["answer"]
    assert body["citations"]
    assert body["citations"][0]["document_id"] == doc["id"]
    assert body["citations"][0]["page_start"] >= 1
    assert body["citations"][0]["section"]

    detail = client.get(f"/api/v1/chat/sessions/{session_id}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assistant = detail["messages"][1]
    assert assistant["grounding"] == "supported_by_source"
    assert assistant["citations"]


def test_ask_absent_answer_not_found(client, app_settings):
    _upload(client)
    app_settings.llm.provider = "stub"
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]

    resp = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "How do whales photosynthesise underwater?"},
    )
    body = resp.json()
    assert body["grounding"] == "not_found"
    assert body["answer"] == "I don't know from the provided sources."
    assert body["citations"] == []


def test_ask_misleading_question_inference(client, app_settings):
    _upload(client)
    app_settings.llm.provider = "stub"
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    resp = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "This question is misleading: is the sky cheese?"},
    )
    assert resp.json()["grounding"] == "inference"


def test_ask_contradictory_sources_inference(client, app_settings):
    _upload(client)
    app_settings.llm.provider = "stub"
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    resp = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "Do the sources contradict each other here?"},
    )
    assert resp.json()["grounding"] == "inference"


def test_conversation_history_preserved(client, app_settings):
    _upload(client)
    app_settings.llm.provider = "stub"
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "First question about memory."},
    )
    client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"question": "Second question about consolidation."},
    )
    detail = client.get(f"/api/v1/chat/sessions/{session_id}").json()
    assert len(detail["messages"]) == 4


def test_delete_session(client, app_settings):
    _upload(client)
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    assert client.delete(f"/api/v1/chat/sessions/{session_id}").status_code == 204
    assert client.get(f"/api/v1/chat/sessions/{session_id}").status_code == 404


def test_missing_session_404(client):
    assert client.get("/api/v1/chat/sessions/does-not-exist").status_code == 404
