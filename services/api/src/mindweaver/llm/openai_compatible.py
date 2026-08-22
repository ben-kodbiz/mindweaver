"""OpenAI-compatible LLM provider.

Ollama (``/v1/chat/completions``), llama.cpp server, LM Studio, and OpenAI
all speak the same chat-completions protocol; one provider covers them, with
the base URL chosen by configuration.
"""

from __future__ import annotations

import httpx

from mindweaver.config import Settings
from mindweaver.llm.base import LLMMessage, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm.base_url.rstrip("/")
        self.model_name = settings.llm.model
        self._timeout = settings.llm.timeout_seconds

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        if not self.model_name:
            raise ValueError("LLM__MODEL is not configured")

        payload = {
            "model": self.model_name,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        try:
            content: str = body["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected LLM response: {body!r}") from exc
