"""Stage 2: model gateway abstraction for the intelligence layer.

A single entry point (`IntelligenceGateway`) exposing chat, structured
output, tool-calling and image analysis against OpenAI-compatible local
servers. Models declare capabilities up front; every call is capability-
checked before it reaches the network. The HTTP transport is injectable so
tests run against a fake server with no real model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, cast

import httpx

from mindweaver.intelligence.config import IntelligenceConfig, ModelEndpointConfig


class CapabilityError(Exception):
    pass


class GatewayError(Exception):
    """Network/protocol/parse failure surfaced by the gateway."""


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: str  # raw JSON string from the model; validated by the executor


@dataclass(frozen=True)
class GatewayResponse:
    content: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def _require(capabilities: Any, flag: str, role: str) -> None:
    if not getattr(capabilities, flag, False):
        raise CapabilityError(f"the configured {role} model does not declare '{flag}' capability")


class IntelligenceModel:
    """One configured endpoint (text or vision) speaking OpenAI-compatible chat."""

    def __init__(
        self,
        config: ModelEndpointConfig,
        client: httpx.Client,
    ) -> None:
        self.config = config
        self.client = client
        self.capabilities = config.capabilities

    def _post_chat(self, payload: dict[str, Any]) -> GatewayResponse:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        timeout = httpx.Timeout(10.0, read=60.0)
        try:
            response = self.client.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise GatewayError("model request timed out") from exc
        except httpx.HTTPError as exc:
            raise GatewayError(f"model unreachable: {exc}") from exc

        try:
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content")
            raw_calls = message.get("tool_calls") or []
            tool_calls = tuple(
                ToolCallRequest(
                    id=str(call.get("id", "")),
                    name=str(call["function"]["name"]),
                    arguments=str(call["function"].get("arguments", "{}")),
                )
                for call in raw_calls
            )
            return GatewayResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason"),
                raw=body,
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise GatewayError(f"invalid model response: {exc}") from exc

    # -- public API ---------------------------------------------------------

    def chat(self, messages: list[dict[str, Any]], **options: Any) -> GatewayResponse:
        _require(self.capabilities, "chat", self.__class__.__name__)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            **{k: v for k, v in options.items() if v is not None},
        }
        return self._post_chat(payload)

    def structured(
        self, messages: list[dict[str, Any]], schema: dict[str, Any], **options: Any
    ) -> dict[str, Any]:
        _require(self.capabilities, "structured_output", type(self).__name__)
        response = self.chat(messages, **options)
        text = response.content or ""
        try:
            start, end = text.find("{"), text.rfind("}")
            parsed = cast(dict[str, Any], json.loads(text[start : end + 1]))
        except Exception as exc:
            raise GatewayError(f"model returned invalid JSON: {text[:120]!r}") from exc
        missing = [key for key in schema.get("required", []) if key not in parsed]
        if missing:
            raise GatewayError(f"model JSON missing keys: {missing}")
        return parsed

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **options: Any,
    ) -> GatewayResponse:
        _require(self.capabilities, "tool_calling", type(self).__name__)
        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": [{"type": "function", "function": t} for t in tools],
            **{k: v for k, v in options.items() if v is not None},
        }
        return self._post_chat(payload)

    def analyze_image(self, image_b64: str, prompt: str, **options: Any) -> GatewayResponse:
        _require(self.capabilities, "vision", type(self).__name__)
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
            ],
        }
        return self.chat([message], **options)


class IntelligenceGateway:
    """Aggregates the configured text + vision endpoints."""

    def __init__(
        self,
        config: IntelligenceConfig,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.client = client or httpx.Client()

    @cached_property
    def text(self) -> IntelligenceModel:
        return IntelligenceModel(self.config.text, self.client)

    @cached_property
    def vision(self) -> IntelligenceModel:
        return IntelligenceModel(self.config.vision, self.client)
