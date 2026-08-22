"""Intelligence gateway unit tests (Stage 2) — uses httpx.MockTransport."""

import json

import httpx
import pytest
from mindweaver.intelligence.config import (
    IntelligenceConfig,
    ModelCapabilities,
    ModelEndpointConfig,
)
from mindweaver.intelligence.gateway import (
    CapabilityError,
    GatewayError,
    IntelligenceGateway,
)


def _config(**cap_overrides) -> IntelligenceConfig:
    caps = {"chat": True, "vision": False, "structured_output": True, "tool_calling": True}
    caps.update(cap_overrides)
    return IntelligenceConfig(
        text={
            "enabled": True,
            "base_url": "http://fake/v1",
            "model": "text-m",
            "capabilities": caps,
        }
    )


def _gateway_with(handler, config=None) -> IntelligenceGateway:
    transport = httpx.MockTransport(handler)
    return IntelligenceGateway(config or _config(), client=httpx.Client(transport=transport))


def _chat_response(content="hello", tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
        message["content"] = content
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


def test_chat_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/chat/completions" in str(request.url)
        body = json.loads(request.read())
        assert body["model"] == "text-m"
        return httpx.Response(200, json=_chat_response("hello world"))

    gw = _gateway_with(handler)
    response = gw.text.chat([{"role": "user", "content": "hi"}])
    assert response.content == "hello world"


def test_structured_output_parses_json():
    def handler(request):
        payload = {"items": [{"label": "Memory"}]}
        return httpx.Response(200, json=_chat_response(json.dumps(payload)))

    gw = _gateway_with(handler)
    result = gw.text.structured([{"role": "user", "content": "go"}], schema={"required": ["items"]})
    assert result["items"][0]["label"] == "Memory"


def test_structured_invalid_json_raises():
    gw = _gateway_with(lambda req: httpx.Response(200, json=_chat_response("not json")))
    with pytest.raises(GatewayError, match="invalid JSON"):
        gw.text.structured([], schema={})


def test_tool_call_response():
    calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "search_document", "arguments": '{"query":"memory"}'},
        }
    ]

    def handler(request):
        return httpx.Response(200, json=_chat_response(tool_calls=calls))

    gw = _gateway_with(handler)
    response = gw.text.chat_with_tools(
        [{"role": "user", "content": "find stuff"}],
        tools=[{"name": "search_document", "description": "d", "parameters": {}}],
    )
    assert response.has_tool_calls is True
    assert response.tool_calls[0].name == "search_document"
    assert json.loads(response.tool_calls[0].arguments)["query"] == "memory"


def test_vision_request_sends_image_url():
    seen_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.read()))
        return httpx.Response(200, json=_chat_response("a diagram"))

    config = _config(vision=True)
    vision_caps = ModelEndpointConfig(
        enabled=True,
        base_url="http://fake/v1",
        model="vision-m",
        capabilities=ModelCapabilities(chat=True, vision=True),
    )
    intel = IntelligenceConfig(
        text=config.text,
        vision=vision_caps if isinstance(vision_caps, dict) else vision_caps,
    )
    from mindweaver.intelligence.gateway import IntelligenceModel

    model = IntelligenceModel(intel.vision, httpx.Client(transport=httpx.MockTransport(handler)))
    response = model.analyze_image("abc123", "describe this")
    assert response.content == "a diagram"

    content_parts = seen_payloads[0]["messages"][0]["content"]
    assert any(part["type"] == "image_url" for part in content_parts)
    image_parts = [p for p in content_parts if p["type"] == "image_url"]
    assert image_parts
    assert "base64" in image_parts[0]["image_url"]["url"]


def test_connection_failure_raises_gateway_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    gw = _gateway_with(handler)
    with pytest.raises(GatewayError, match="unreachable"):
        gw.text.chat([])


def test_timeout_raises_gateway_error():
    def handler(request):
        raise httpx.ReadTimeout("timed out")

    gw = _gateway_with(handler)
    with pytest.raises(GatewayError, match="timed out"):
        gw.text.chat([])


def test_capability_mismatch_vision_on_text_model():
    gw = _gateway_with(lambda req: httpx.Response(200, json={}))
    with pytest.raises(CapabilityError, match="vision"):
        gw.text.analyze_image("abc", "prompt")


def test_invalid_model_response_shape():
    gw = _gateway_with(lambda req: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(GatewayError, match="invalid model response"):
        gw.text.chat([])
