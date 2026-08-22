import pytest
from mindweaver.config import AppConfig, DatabaseConfig, SecurityConfig, Settings
from pydantic import ValidationError


def test_default_config_is_valid():
    settings = Settings()
    assert settings.app.environment == "development"
    assert settings.app.api_v1_prefix == "/api/v1"
    assert settings.database.url.startswith("sqlite")
    assert settings.llm.provider == "ollama"
    assert settings.embeddings.provider == "local"
    assert settings.ocr.provider == "rapidocr"
    assert settings.reranker.enabled is True
    assert settings.document_processor.backend == "pypdf"
    assert settings.tts.provider == "kokoro"


def test_environment_overrides_nested_config(monkeypatch):
    monkeypatch.setenv("MINDWEAVER_APP__ENVIRONMENT", "testing")
    monkeypatch.setenv("MINDWEAVER_LLM__BASE_URL", "http://example:11434")
    settings = Settings()
    assert settings.app.environment == "testing"
    assert settings.llm.base_url == "http://example:11434"


def test_invalid_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(app=AppConfig(environment="bogus"))


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValidationError):
        Settings(app=AppConfig(log_level="NOT_A_LEVEL"))


def test_invalid_database_url_is_rejected():
    with pytest.raises(ValidationError):
        Settings(database=DatabaseConfig(url="this is not a url"))


def test_production_requires_custom_secret_key():
    with pytest.raises(ValidationError):
        Settings(app=AppConfig(environment="production"))


def test_production_allows_custom_secret_key():
    settings = Settings(
        app=AppConfig(environment="production"),
        security=SecurityConfig(secret_key="a-real-secret"),
    )
    assert settings.app.environment == "production"
