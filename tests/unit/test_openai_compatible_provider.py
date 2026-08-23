"""Tests for OpenAICompatibleProvider response handling."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mindweaver.config import Settings
from mindweaver.llm.base import LLMMessage
from mindweaver.llm.openai_compatible import OpenAICompatibleProvider


class _Response:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


def _provider(monkeypatch: pytest.MonkeyPatch, body: dict[str, Any], **llm_kwargs: Any):
    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, json: dict[str, Any], timeout: float) -> _Response:
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return _Response(body)

    monkeypatch.setattr("mindweaver.llm.openai_compatible.httpx.post", _fake_post)
    settings = Settings.model_construct()
    settings.llm.provider = "lmstudio"
    settings.llm.base_url = "http://localhost:1234"
    settings.llm.model = "test-model"
    for key, value in llm_kwargs.items():
        setattr(settings.llm, key, value)
    provider = OpenAICompatibleProvider(settings)
    return provider, captured


def test_complete_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"choices": [{"message": {"content": '{"answer": "hi"}'}, "finish_reason": "stop"}]}
    provider, _ = _provider(monkeypatch, body)
    result = provider.complete([LLMMessage(role="user", content="q")])
    assert result == '{"answer": "hi"}'


def test_complete_falls_back_to_reasoning_content(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "choices": [
            {
                "message": {"content": "", "reasoning_content": 'thinking... {"a": 1}'},
                "finish_reason": "length",
            }
        ]
    }
    provider, _ = _provider(monkeypatch, body)
    result = provider.complete([LLMMessage(role="user", content="q")])
    assert result == 'thinking... {"a": 1}'


def test_complete_extra_body_is_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    provider, captured = _provider(monkeypatch, body, extra_body=extra)
    result = provider.complete([LLMMessage(role="user", content="q")])
    assert result == "ok"
    assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"


def test_extra_body_parses_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MINDWEAVER_LLM__EXTRA_BODY",
        json.dumps({"chat_template_kwargs": {"enable_thinking": False}}),
    )
    settings = Settings()
    assert settings.llm.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
