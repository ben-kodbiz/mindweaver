"""Stages 7+10: intelligence API integration and end-to-end scenario."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fixtures.pdf import make_search_book_pdf

# --- fake model server ------------------------------------------------------


class _FakeModelHandler(BaseHTTPRequestHandler):
    responses: list[dict] = []
    request_count = 0
    lock = threading.Lock()

    def do_POST(self):
        with self.lock:
            _FakeModelHandler.request_count += 1
            index = min(_FakeModelHandler.request_count - 1, len(self.responses) - 1)
        inner = self.responses[index]
        message = {"role": "assistant", "content": inner.get("content")}
        if inner.get("tool_calls"):
            message["tool_calls"] = inner["tool_calls"]
        body = json.dumps({"choices": [{"message": message, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def intel_client(client, app_settings):
    """Client with intelligence enabled + fake model server."""
    server = HTTPServer(("localhost", 0), _FakeModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://localhost:{server.server_port}/v1"

    app_settings.llm.provider = "stub"
    app_settings.intelligence.enabled = True
    app_settings.intelligence.text.enabled = True
    app_settings.intelligence.text.base_url = base_url
    app_settings.intelligence.text.model = "fake-text"
    app_settings.intelligence.vision.enabled = True
    app_settings.intelligence.vision.base_url = base_url
    app_settings.intelligence.vision.model = "fake-vision"
    app_settings.intelligence.tools.enabled = True
    app_settings.intelligence.node_expansion.enabled = True

    # Build and inject the gateway so routes can use it.
    from mindweaver.intelligence.gateway import IntelligenceGateway

    gateway = IntelligenceGateway(app_settings.intelligence)
    # Replace httpx client with one that talks to our fake server port.
    import httpx as _httpx

    class _RoutedClient(_httpx.Client):
        """Redirects all requests to the fake model server."""

        def __init__(self):
            super().__init__(base_url=base_url)

    gateway.client = _RoutedClient()
    gateway.text.client = gateway.client
    gateway.vision.client = gateway.client

    client.app.state.intelligence_gateway = gateway
    yield client
    server.shutdown()


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_disabled_by_default(client):
    resp = client.get("/api/v1/intelligence/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_expand_disabled_returns_flagged_error(client):
    doc = _upload(client)
    resp = client.post(
        f"/api/v1/intelligence/mindmap/expand?document_id={doc['id']}&node_id=test-node"
    )
    assert resp.status_code == 409
    assert "disabled" in resp.json()["error"]["message"].lower()


def test_status_enabled(intel_client):
    _upload(intel_client)
    resp = intel_client.get("/api/v1/intelligence/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["text_model"]["enabled"] is True
    assert body["tools"]["enabled"] is True


def test_models_endpoint(intel_client):
    resp = intel_client.get("/api/v1/intelligence/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "lmstudio-local" in body.get("presets", [])


def test_e2e_expand_and_accept(intel_client):
    """Full pipeline: upload → searchable → expand with AI → accept child."""
    doc = _upload(intel_client)

    # Document is searchable
    search_resp = intel_client.get("/api/v1/search", params={"q": "memory consolidation"})
    assert search_resp.json()["total"] >= 1

    # Get a real node id from the graph
    graph = intel_client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    assert graph["nodes"]
    target_node_id = graph["nodes"][0]["id"]

    # Use a real chunk id from this document so the proposal validates.
    chunks = intel_client.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert chunks
    real_chunk_id = chunks[0]["chunk_id"]

    # Set up fake model: first call search_document, then produce children
    _FakeModelHandler.responses = [
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "search_document",
                        "arguments": json.dumps({"query": "consolidation memory"}),
                    },
                }
            ],
            "content": None,
        },
        {
            "content": json.dumps(
                {
                    "children": [
                        {
                            "label": "AI Proposed Concept",
                            "relationship": "related_to",
                            "description": "proposed by AI after tool use",
                            "evidence": [{"chunk_id": real_chunk_id}],
                        }
                    ]
                }
            ),
        },
    ]

    expand_resp = intel_client.post(
        f"/api/v1/intelligence/mindmap/expand?document_id={doc['id']}&node_id={target_node_id}"
    )
    if expand_resp.status_code != 200:
        print("EXPAND ERROR:", expand_resp.text[:500])
    assert expand_resp.status_code == 200
    proposal = expand_resp.json()["proposal"]
    assert proposal["children"]
    assert proposal["children"][0]["label"] == "AI Proposed Concept"

    # Accept the proposed node (with empty evidence for testing)
    accepted_child = {
        **proposal["children"][0],
        "evidence": [],
    }
    accept_resp = intel_client.post(
        f"/api/v1/intelligence/mindmap/nodes/{target_node_id}/accept?document_id={doc['id']}",
        json={"children": [accepted_child]},
    )
    assert accept_resp.status_code == 200, accept_resp.text
    assert accept_resp.json()["accepted_count"] >= 1

    # Verify the accepted node exists in the graph
    final_graph = intel_client.get(f"/api/v1/documents/{doc['id']}/graph").json()
    labels = {n["label"] for n in final_graph["nodes"]}
    assert "AI Proposed Concept" in labels


# --- regression: intelligence completely disabled ---


def test_vision_analyze_disabled_returns_409(client):
    doc = _upload(client)
    resp = client.post(
        "/api/v1/intelligence/vision/analyze",
        json={"document_id": doc["id"], "page_number": 1},
    )
    assert resp.status_code == 409
    assert "disabled" in resp.json()["error"]["message"].lower()


def test_accept_proposal_disabled_returns_409(client):
    doc = _upload(client)
    resp = client.post(
        "/api/v1/intelligence/mindmap/nodes/topic:test/accept?document_id=" + doc["id"],
        json={"children": [{"label": "x"}]},
    )
    assert resp.status_code == 409
    assert "disabled" in resp.json()["error"]["message"].lower()


def test_health_endpoint_disabled(client):
    resp = client.get("/api/v1/intelligence/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False


def test_no_intelligence_gateway_by_default(client):
    """Gateway must not be mounted unless explicitly enabled."""
    assert getattr(client.app.state, "intelligence_gateway", None) is None
