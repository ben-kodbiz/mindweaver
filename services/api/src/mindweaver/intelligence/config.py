"""Configuration for the optional Vision + Tool-Calling Intelligence Layer.

Everything here defaults to DISABLED so the existing application behaviour is
unchanged until a user explicitly turns the layer on. The layer can also be
removed entirely by deleting this package plus one router registration.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, model_validator

ALLOWED_PROVIDERS = {"openai-compatible"}

PRESETS: dict[str, dict[str, Any]] = {
    "lmstudio-local": {
        "provider": "openai-compatible",
        "base_url": "http://localhost:1234/v1",
        "capabilities": {
            "chat": True,
            "vision": False,
            "structured_output": True,
            "tool_calling": True,
        },
    },
    "llamacpp-local": {
        "provider": "openai-compatible",
        "base_url": "http://localhost:8080/v1",
        "capabilities": {
            "chat": True,
            "vision": False,
            "structured_output": True,
            "tool_calling": True,
        },
    },
}

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in _TRUE_VALUES


class ModelCapabilities(BaseModel):
    """Defaults match a capable local *text* model; vision models opt in."""

    chat: bool = True
    vision: bool = False
    structured_output: bool = True
    tool_calling: bool = True


class ModelEndpointConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai-compatible"
    preset: str | None = None
    base_url: str = ""
    model: str = ""
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)

    @model_validator(mode="before")
    @classmethod
    def _apply_preset(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("preset"):
            preset = PRESETS.get(str(data["preset"]))
            if preset is None:
                raise ValueError(f"unknown preset: {data['preset']}")
            merged = {**preset, **{k: v for k, v in data.items() if v not in (None, "")}}
            return merged
        return data

    @model_validator(mode="after")
    def _validate(self) -> ModelEndpointConfig:
        if not self.enabled:
            return self
        if self.provider not in ALLOWED_PROVIDERS:
            raise ValueError(
                f"invalid provider '{self.provider}'; allowed: {sorted(ALLOWED_PROVIDERS)}"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"invalid base_url: {self.base_url!r}")
        if not self.model.strip():
            raise ValueError("model name must be set when the endpoint is enabled")
        return self


class ToolsConfig(BaseModel):
    enabled: bool = False
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_tool_calls: int = Field(default=10, ge=1, le=50)
    timeout_seconds: float = Field(default=30.0, gt=0)


class VisionAnalysisTriggers(BaseModel):
    low_ocr_confidence: bool = True
    complex_layout: bool = True
    tables: bool = True
    diagrams: bool = True


class VisionAnalysisConfig(BaseModel):
    enabled: bool = False
    analyze_all_pages: bool = False
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    triggers: VisionAnalysisTriggers = Field(default_factory=VisionAnalysisTriggers)


class NodeExpansionConfig(BaseModel):
    enabled: bool = False
    require_evidence: bool = True
    max_children: int = Field(default=8, ge=1, le=32)


class IntelligenceConfig(BaseModel):
    """Optional Vision + Tool-Calling layer. Disabled by default."""

    enabled: bool = False
    text: ModelEndpointConfig = Field(default_factory=ModelEndpointConfig)
    vision: ModelEndpointConfig = Field(default_factory=ModelEndpointConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    vision_analysis: VisionAnalysisConfig = Field(default_factory=VisionAnalysisConfig)
    node_expansion: NodeExpansionConfig = Field(default_factory=NodeExpansionConfig)

    @model_validator(mode="before")
    @classmethod
    def _apply_mw_env_overrides(cls, data: Any) -> Any:
        values: dict[str, Any] = dict(data) if isinstance(data, dict) else {}

        def section(name: str) -> dict[str, Any]:
            current = values.get(name)
            return dict(current) if isinstance(current, dict) else {}

        override = _env_bool("MW_INTELLIGENCE_ENABLED")
        if override is not None:
            values["enabled"] = override

        text = section("text")
        if (v := _env_bool("MW_TEXT_MODEL_ENABLED")) is not None:
            text["enabled"] = v
        if os.getenv("MW_TEXT_MODEL_BASE_URL"):
            text["base_url"] = os.environ["MW_TEXT_MODEL_BASE_URL"]
        if os.getenv("MW_TEXT_MODEL_NAME"):
            text["model"] = os.environ["MW_TEXT_MODEL_NAME"]
        if text:
            values["text"] = text

        vision = section("vision")
        if (v := _env_bool("MW_VISION_MODEL_ENABLED")) is not None:
            vision["enabled"] = v
        if os.getenv("MW_VISION_MODEL_BASE_URL"):
            vision["base_url"] = os.environ["MW_VISION_MODEL_BASE_URL"]
        if os.getenv("MW_VISION_MODEL_NAME"):
            vision["model"] = os.environ["MW_VISION_MODEL_NAME"]
        if vision:
            values["vision"] = vision

        tools = section("tools")
        if (v := _env_bool("MW_TOOLS_ENABLED")) is not None:
            tools["enabled"] = v
        if tools:
            values["tools"] = tools

        vision_analysis = section("vision_analysis")
        if (v := _env_bool("MW_VISION_ENABLED")) is not None:
            vision_analysis["enabled"] = v
        if vision_analysis:
            values["vision_analysis"] = vision_analysis

        return values

    @model_validator(mode="after")
    def _validate_enabled_consistency(self) -> IntelligenceConfig:
        if self.enabled:
            problems: list[str] = []
            if self.text.enabled and (
                not self.text.capabilities.chat or not self.text.capabilities.tool_calling
            ):
                problems.append("text model must declare chat + tool_calling capabilities")
            if self.vision.enabled and not self.vision.capabilities.vision:
                problems.append("vision model must declare vision capability")
            if self.tools.enabled and not self.text.enabled:
                problems.append("tools require an enabled text model")
            if self.node_expansion.enabled and not self.text.enabled:
                problems.append("node expansion requires an enabled text model")
            if self.vision_analysis.enabled and not self.vision.enabled:
                problems.append("vision analysis requires an enabled vision model")
            if problems:
                raise ValueError("; ".join(problems))
        return self
