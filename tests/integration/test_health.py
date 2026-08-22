def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_endpoint(client):
    resp = client.get("/api/v1/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "mindweaver"
    assert body["version"] == "0.1.0"
    assert body["api_version"] == "v1"


def test_readiness_ok(client):
    resp = client.get("/api/v1/readiness")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["checks"]["database"] == "ok"


def test_response_includes_request_id(client):
    resp = client.get("/api/v1/health")
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"]


def test_404_returns_structured_error(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["request_id"] == resp.headers["X-Request-ID"]


def test_validation_error_is_structured(client):
    resp = client.post("/api/v1/echo", json={"message": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_echo_roundtrip(client):
    resp = client.post("/api/v1/echo", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"message": "hello"}
