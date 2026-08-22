"""Stage 3: safe tool registry and executor.

The model never executes code. It requests a named tool with arguments; the
registry validates the request against the tool's schema, enforces document
scope and limits, executes it with a timeout, logs the call, and returns a
structured result.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, Field, ValidationError, create_model

logger = logging.getLogger("intelligence.tool")


class ToolError(Exception):
    """Safe, user-visible failure of a tool invocation."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # lightweight JSON-schema-ish definition


@dataclass
class ToolContext:
    """Everything a tool is allowed to touch. Scoped to specific documents."""

    session: Any  # sqlalchemy Session
    settings: Any
    document_ids: tuple[str, ...]

    def assert_document(self, document_id: str) -> None:
        if document_id not in self.document_ids:
            raise ToolError(f"access to document '{document_id}' is outside the allowed scope")


@dataclass
class ToolResult:
    name: str
    ok: bool
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    model = _argument_model(spec)
    try:
        parsed = model.model_validate(arguments)
    except ValidationError as exc:
        raise ToolError(f"invalid arguments for {spec.name}: {exc}") from exc
    return parsed.model_dump()


_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}

_SPEC_MODELS: dict[str, type[BaseModel]] = {}


def _argument_model(spec: ToolSpec) -> type[BaseModel]:
    cached = _SPEC_MODELS.get(spec.name)
    if cached is not None:
        return cached

    properties = spec.parameters.get("properties", {})
    required = set(spec.parameters.get("required", []))

    fields: dict[str, Any] = {}
    for arg_name, arg_def in properties.items():
        annotation = _TYPE_MAP.get(arg_def.get("type"), Any)
        if arg_name in required:
            fields[arg_name] = (annotation, ...)
        else:
            fields[arg_name] = (annotation, Field(default=arg_def.get("default")))

    model = cast(type[BaseModel], create_model(f"{spec.name}Args", **fields))
    _SPEC_MODELS[spec.name] = model
    return model


class ToolRegistry:
    def __init__(self, max_limit_value: int = 50) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}
        self._max_limit = max_limit_value

    def register(self, spec: ToolSpec, func: Callable[..., Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = (spec, func)

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec, _ in self._tools.values()
        ]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    # -- execution ----------------------------------------------------------

    def execute(
        self,
        context: ToolContext,
        name: str,
        raw_arguments: str | dict[str, Any],
        *,
        timeout_seconds: float = 30.0,
    ) -> ToolResult:
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        if name not in self._tools:
            logger.warning("intelligence.tool.call rejected unknown=%s", name)
            return ToolResult(name=name, ok=False, error=f"unknown tool: {name}")

        spec, func = self._tools[name]
        if isinstance(raw_arguments, str):
            try:
                arguments: dict[str, Any] = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError as exc:
                return ToolResult(name=name, ok=False, error=f"invalid JSON args: {exc}")
        else:
            arguments = dict(raw_arguments)

        try:
            parsed = _validate_arguments(spec, arguments)
        except ToolError as exc:
            logger.warning("intelligence.tool.call failure=%s", exc)
            return ToolResult(name=name, ok=False, error=str(exc), duration_ms=elapsed())

        # Clamp obvious limit-style integers to sane bounds.
        if "limit" in parsed and isinstance(parsed["limit"], int):
            parsed["limit"] = max(1, min(parsed["limit"], self._max_limit))

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(func, context, **parsed)
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeout:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            logger.warning("intelligence.tool.failure timeout tool=%s", name)
            return ToolResult(name=name, ok=False, error="tool timed out", duration_ms=elapsed())
        finally:
            executor.shutdown(wait=False)

        duration = elapsed()
        logger.info("intelligence.tool.success tool=%s duration_ms=%s", name, duration)
        return ToolResult(name=name, ok=True, result=result, duration_ms=duration)
