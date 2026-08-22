"""Stage 3: safe tool registry tests."""

import time

from mindweaver.intelligence.tools.registry import ToolRegistry, ToolSpec


def _registry(slow=False) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_document",
            description="Search",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        lambda ctx, query, limit=5: {"hits": [f"result for {query}"], "limit": limit},
    )
    if slow:
        registry.register(
            ToolSpec(
                name="slow_tool",
                description="Slow",
                parameters={"type": "object", "properties": {}},
            ),
            lambda ctx: time.sleep(10),
        )
    return registry


class _Ctx:
    document_ids = ("doc_1",)
    session = None
    settings = None


def test_known_tool_executes():
    result = _registry().execute(_Ctx(), "search_document", '{"query": "memory"}')
    assert result.ok is True
    assert result.result["hits"] == ["result for memory"]


def test_unknown_tool_rejected():
    result = _registry().execute(_Ctx(), "nope", "{}")
    assert result.ok is False
    assert "unknown tool" in result.error


def test_invalid_json_arguments_rejected():
    result = _registry().execute(_Ctx(), "search_document", "{broken")
    assert result.ok is False
    assert "invalid JSON" in (result.error or "")


def test_missing_required_argument_rejected():
    result = _registry().execute(_Ctx(), "search_document", "{}")
    assert result.ok is False
    assert "invalid arguments" in (result.error or "")


def test_limit_clamped():
    registry = _registry()
    result = registry.execute(_Ctx(), "search_document", '{"query": "x", "limit": 99999}')
    assert result.ok is True
    assert result.result["limit"] == 50


def test_tool_timeout():
    result = _registry(slow=True).execute(_Ctx(), "slow_tool", "{}", timeout_seconds=0.1)
    assert result.ok is False
    assert "timed out" in (result.error or "")


def test_specs_exposed_for_model():
    specs = _registry().specs()
    names = [s["name"] for s in specs]
    assert "search_document" in names
