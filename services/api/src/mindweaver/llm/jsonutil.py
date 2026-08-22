"""Shared helpers for parsing structured LLM output."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def extract_json(content: str) -> dict[str, Any] | None:
    """Parse a JSON object out of an LLM response.

    Handles plain JSON, markdown-fenced blocks, and JSON surrounded by prose.
    Reasoning models may inline ``<think>`` blocks; they are stripped first so
    braces inside deliberation cannot masquerade as the answer.
    Returns ``None`` when no JSON object can be extracted.
    """
    text = _THINK_BLOCK.sub("", content or "").strip()
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None
