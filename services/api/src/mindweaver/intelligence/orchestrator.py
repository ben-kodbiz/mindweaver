"""Stage 6: tool-calling orchestrator (bounded agent loop)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from mindweaver.intelligence.gateway import (
    GatewayError,
    IntelligenceModel,
)
from mindweaver.intelligence.tools.registry import ToolRegistry

logger = logging.getLogger("intelligence.orchestrator")


@dataclass
class OrchestratorLimits:
    max_iterations: int = 5
    max_tool_calls: int = 10
    timeout_seconds: float = 30.0


@dataclass
class OrchestratorResult:
    final_text: str = ""
    tool_calls_made: int = 0
    iterations: int = 0
    stopped_reason: str = "completed"
    tool_log: list[dict[str, Any]] = field(default_factory=list)


def run_orchestrator_with_context(
    model: IntelligenceModel,
    registry: ToolRegistry,
    context: Any,
    messages: list[dict[str, Any]],
    limits: OrchestratorLimits,
) -> OrchestratorResult:
    """Same loop as :func:`run_orchestrator` but with a bound tool context."""
    result = OrchestratorResult()
    conversation = [dict(message) for message in messages]
    specs = registry.specs()

    while result.iterations < limits.max_iterations:
        if result.tool_calls_made >= limits.max_tool_calls:
            result.stopped_reason = "tool_call_limit"
            break

        try:
            response = model.chat_with_tools(conversation, specs)
        except GatewayError as exc:
            logger.warning("intelligence.model.response error=%s", exc)
            result.stopped_reason = f"model_error: {exc}"
            return result
        result.iterations += 1

        if not response.has_tool_calls:
            result.final_text = response.content or ""
            return result

        conversation.append(
            {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in response.tool_calls
                ],
            }
        )

        stop = False
        for call in response.tool_calls:
            if result.tool_calls_made >= limits.max_tool_calls:
                result.stopped_reason = "tool_call_limit"
                stop = True
                break

            started = time.monotonic()
            tool_result = registry.execute(
                context,
                call.name,
                call.arguments,
                timeout_seconds=limits.timeout_seconds,
            )
            result.tool_calls_made += 1

            logger.info(
                "intelligence.tool.call tool=%s ok=%s duration_ms=%d",
                call.name,
                tool_result.ok,
                int((time.monotonic() - started) * 1000),
            )
            result.tool_log.append(
                {"tool": call.name, "ok": tool_result.ok, "error": tool_result.error}
            )

            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(
                        {
                            "ok": tool_result.ok,
                            "result": tool_result.result,
                            "error": tool_result.error,
                        },
                        default=str,
                    ),
                }
            )

        if stop:
            break

    else:
        result.stopped_reason = "iteration_limit"

    return result
