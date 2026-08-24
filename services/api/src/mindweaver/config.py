"""Application configuration.

Settings are loaded from environment variables with the ``MINDWEAVER_``
prefix and ``__`` as the nested-field separator (e.g.
``MINDWEAVER_LLM__BASE_URL``) plus an optional ``.env`` file.

Configuration is validated eagerly: constructing a :class:`Settings` raises
``ValidationError`` for invalid values.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from mindweaver.intelligence.config import IntelligenceConfig

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

Environment = Literal["development", "testing", "production"]


class AppConfig(BaseModel):
    name: str = "mindweaver"
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    @model_validator(mode="after")
    def _validate_log_level(self) -> AppConfig:
        if self.log_level.upper() not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown log level: {self.log_level}")
        return self


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/mindweaver.db"
    echo: bool = False

    @model_validator(mode="after")
    def _validate_url(self) -> DatabaseConfig:
        try:
            make_url(self.url)
        except Exception as exc:
            raise ValueError(f"invalid database URL: {self.url}") from exc
        return self


class StorageConfig(BaseModel):
    root_dir: Path = Path("./data")
    originals_dir: Path = Path("./data/originals")
    derived_dir: Path = Path("./data/derived")
    max_upload_bytes: int = 500 * 1024 * 1024


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = ""
    timeout_seconds: float = 300.0
    temperature: float = 0.2
    # Extra JSON body merged into each chat-completions request (server/model
    # specific knobs, e.g. ``{"chat_template_kwargs": {"enable_thinking":
    # false}}`` for Qwen reasoning models served by LM Studio).
    extra_body: dict[str, Any] = Field(default_factory=dict)


class EmbeddingsConfig(BaseModel):
    provider: str = "local"
    model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    dimension: int = 512


class RerankerConfig(BaseModel):
    provider: str = "local"
    model: str = ""
    enabled: bool = True


class SearchConfig(BaseModel):
    fts_weight: float = 0.4
    vector_weight: float = 0.6
    keyword_limit: int = 30
    vector_limit: int = 30
    default_limit: int = 10
    min_score: float = 0.05


class ChatConfig(BaseModel):
    evidence_limit: int = 5
    max_tokens: int = 2048


class GraphConfig(BaseModel):
    max_chunks: int = 40
    max_nodes: int = 100
    max_tokens: int = 4096


HardwareProfile = Literal["low", "medium", "high"]


class MindMapConfig(BaseModel):
    max_topics: int = 8
    max_concepts_per_topic: int = 3
    max_depth: int = 2


class OCRConfig(BaseModel):
    provider: str = "rapidocr"
    languages: list[str] = Field(default_factory=lambda: ["en"])
    min_confidence: float = 0.5
    render_scale: float = 2.5


class DocumentProcessorConfig(BaseModel):
    backend: str = "pypdf"
    ocr_enabled: bool = True

    @model_validator(mode="after")
    def _validate_backend(self) -> DocumentProcessorConfig:
        if self.backend.lower() not in {"pypdf", "native", "hybrid", "docling"}:
            raise ValueError(f"unknown document processor backend: {self.backend}")
        return self


class ChunkingConfig(BaseModel):
    max_chars: int = 2000
    min_chars: int = 100


class TTSConfig(BaseModel):
    provider: str = "kokoro"


class WorkerConfig(BaseModel):
    concurrency: int = 2


class SecurityConfig(BaseModel):
    secret_key: str = "change-me"
    cors_origins: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    document_processor: DocumentProcessorConfig = Field(default_factory=DocumentProcessorConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    mindmap: MindMapConfig = Field(default_factory=MindMapConfig)
    intelligence: IntelligenceConfig = Field(default_factory=lambda: IntelligenceConfig())
    hardware_profile: HardwareProfile = "medium"
    tts: TTSConfig = Field(default_factory=TTSConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    model_config = SettingsConfigDict(
        env_prefix="MINDWEAVER_",
        env_nested_delimiter="__",
        env_file=[str(_REPO_ROOT / ".env"), ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _apply_hardware_profile(self) -> Settings:
        """Presets tune provider choices for the target hardware."""
        if self.hardware_profile == "low":
            self.reranker.enabled = False
            self.embeddings.provider = "local"
            self.embeddings.dimension = min(self.embeddings.dimension, 256)
            self.search.vector_weight = 0.3
            self.search.fts_weight = 0.7
            self.chat.evidence_limit = 4
            self.graph.max_chunks = 20
            self.worker.concurrency = 1
        elif self.hardware_profile == "high":
            self.embeddings.provider = "sentence-transformers"
            self.search.fts_weight = 0.35
            self.search.vector_weight = 0.65
            self.chat.evidence_limit = 8
            self.document_processor.backend = "docling"
        return self

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> Settings:
        if self.app.environment == "production" and self.security.secret_key == "change-me":
            raise ValueError(
                "MINDWEAVER_SECURITY__SECRET_KEY must be set when running in production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
