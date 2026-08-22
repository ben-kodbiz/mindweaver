"""OpenAI-compatible LLM provider.

Ollama (``/v1/chat/completions``), llama.cpp server, LM Studio, and OpenAI
all speak the same chat-completions protocol; one provider covers them, with
the base URL chosen by configuration.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mindweaver.config import Settings
from mindweaver.llm.base import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm.base_url.rstrip("/")
        self.model_name = settings.llm.model
        self._timeout = settings.llm.timeout_seconds
        self._extra_body: dict[str, Any] = dict(settings.llm.extra_body or {})

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        if not self.model_name:
            raise ValueError("LLM__MODEL is not configured")

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Server-specific knobs (e.g. ``chat_template_kwargs`` to disable
        # reasoning on thinking models). Merged last so they win.
        payload.update(self._extra_body)
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected LLM response: {body!r}") from exc

        content: str = message.get("content") or ""
        finish_reason = body["choices"][0].get("finish_reason")
        if not content.strip():
            # Reasoning models (e.g. Qwen thinking variants served by LM Studio)
            # keep their answer in ``reasoning_content`` and may leave
            # ``content`` empty when the token budget is spent on thinking.
            reasoning = message.get("reasoning_content") or ""
            if reasoning.strip():
                logger.warning(
                    "LLM returned empty content (finish_reason=%s); "
                    "falling back to reasoning_content",
                    finish_reason,
                )
                return reasoning
            logger.warning(
                "LLM returned empty content and no reasoning (finish_reason=%s)",
                finish_reason,
            )
        return content
