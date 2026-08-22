"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mindweaver.config import (
    AppConfig,
    DatabaseConfig,
    SecurityConfig,
    Settings,
    StorageConfig,
)
from mindweaver.main import create_app


@pytest.fixture
def app_settings(tmp_path) -> Settings:
    return Settings(
        app=AppConfig(environment="testing"),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path}/test.db"),
        storage=StorageConfig(
            root_dir=tmp_path / "data",
            originals_dir=tmp_path / "data" / "originals",
            derived_dir=tmp_path / "data" / "derived",
        ),
        security=SecurityConfig(secret_key="test-secret"),
    )


@pytest.fixture
def client(app_settings):
    with TestClient(create_app(app_settings)) as client:
        yield client
