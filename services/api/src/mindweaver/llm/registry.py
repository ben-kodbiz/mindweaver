"""LLM provider registry."""

from __future__ import annotations

from mindweaver.config import Settings
from mindweaver.llm.base import LLMProvider


class UnknownLLMProviderError(Exception):
    pass


def get_llm_provider(settings: Settings) -> LLMProvider:
    provider = (settings.llm.provider or "").strip().lower()
    if provider in ("stub", "fake"):
        from mindweaver.llm.stub import StubLLMProvider

        return StubLLMProvider()

    if provider in ("ollama", "llamacpp", "lmstudio", "openai", "openai-compatible"):
        from mindweaver.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(settings)

    raise UnknownLLMProviderError(f"unknown LLM provider: {provider}")
