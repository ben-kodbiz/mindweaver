import pytest
from mindweaver.config import Settings
from mindweaver.llm.registry import UnknownLLMProviderError, get_llm_provider
from mindweaver.llm.stub import StubLLMProvider


def _settings(provider: str) -> Settings:
    settings = Settings.model_construct()
    settings.llm.provider = provider
    return settings


def test_stub_provider_resolves():
    assert isinstance(get_llm_provider(_settings("stub")), StubLLMProvider)


def test_openai_compatible_providers_resolve():
    for provider in ("ollama", "llamacpp", "lmstudio", "openai-compatible"):
        from mindweaver.llm.openai_compatible import OpenAICompatibleProvider

        assert isinstance(get_llm_provider(_settings(provider)), OpenAICompatibleProvider)


def test_unknown_provider_raises():
    with pytest.raises(UnknownLLMProviderError):
        get_llm_provider(_settings("bogus"))


def test_openai_compatible_requires_model():
    from mindweaver.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(_settings("ollama"))
    assert provider.model_name == ""
    from mindweaver.llm.base import LLMMessage

    with pytest.raises(ValueError):
        provider.complete([LLMMessage(role="user", content="hi")])
