"""Stage 1: intelligence feature configuration."""

import pytest
from mindweaver.config import Settings
from mindweaver.intelligence.config import IntelligenceConfig
from pydantic import ValidationError


def test_app_starts_without_intelligence_config():
    settings = Settings(_env_file=None)
    assert settings.intelligence.enabled is False


def test_disabled_by_default():
    config = IntelligenceConfig()
    assert config.enabled is False
    assert config.text.enabled is False
    assert config.vision.enabled is False
    assert config.tools.enabled is False
    assert config.vision_analysis.enabled is False
    assert config.node_expansion.enabled is False


def test_valid_config_loads():
    config = IntelligenceConfig(
        enabled=True,
        text={
            "enabled": True,
            "base_url": "http://localhost:1234/v1",
            "model": "text-model",
        },
        vision={
            "enabled": True,
            "base_url": "http://localhost:1234/v1",
            "model": "vision-model",
            "capabilities": {"chat": True, "vision": True},
        },
        tools={"enabled": True},
        node_expansion={"enabled": True},
        vision_analysis={"enabled": True},
    )
    assert config.text.model == "text-model"
    assert config.vision.capabilities.vision is True
    assert config.tools.enabled is True


def test_invalid_provider_rejected():
    with pytest.raises(ValidationError):
        IntelligenceConfig(
            enabled=True,
            text={
                "enabled": True,
                "provider": "bogus",
                "base_url": "http://localhost:1234/v1",
                "model": "m",
            },
        )


def test_invalid_url_rejected():
    with pytest.raises(ValidationError):
        IntelligenceConfig(
            enabled=True,
            text={"enabled": True, "base_url": "not-a-url", "model": "m"},
        )


def test_enabled_text_model_requires_chat_and_tools_capabilities():
    with pytest.raises(ValidationError):
        IntelligenceConfig(
            enabled=True,
            text={
                "enabled": True,
                "base_url": "http://x/v1",
                "model": "m",
                "capabilities": {"chat": False, "tool_calling": False},
            },
        )


def test_preset_resolves_endpoint(monkeypatch):
    monkeypatch.setenv("MW_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("MW_TEXT_MODEL_ENABLED", "true")
    monkeypatch.setenv("MW_TEXT_MODEL_NAME", "my-model")

    config = IntelligenceConfig(text={"preset": "lmstudio-local"})
    assert config.text.provider == "openai-compatible"
    assert config.text.base_url == "http://localhost:1234/v1"
    assert config.text.model == "my-model"


def test_unknown_preset_rejected():
    with pytest.raises(ValidationError):
        IntelligenceConfig(text={"enabled": True, "preset": "nope", "model": "m"})


def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("MW_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("MW_TEXT_MODEL_ENABLED", "true")
    monkeypatch.setenv("MW_TEXT_MODEL_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("MW_TEXT_MODEL_NAME", "env-model")
    monkeypatch.setenv("MW_TOOLS_ENABLED", "true")

    config = IntelligenceConfig()
    assert config.enabled is True
    assert config.text.base_url == "http://localhost:9999/v1"
    assert config.text.model == "env-model"
    assert config.tools.enabled is True


def test_existing_settings_still_pass():
    settings = Settings()
    assert settings.app.environment in ("development", "testing", "production")
