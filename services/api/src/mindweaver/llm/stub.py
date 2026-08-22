"""Scripted stub LLM provider for tests and offline demos.

Deterministic: inspects the last user message and returns a scripted,
schema-conforming answer so the chat pipeline is testable without a model.
"""

from __future__ import annotations

import json
from typing import Any

from mindweaver.llm.base import LLMMessage, LLMProvider

_MARKERS = {
    "not_found": ("whale", "photosynth", "absent from the sources", "not found"),
    "inference": ("mislead", "contradict"),
}


class StubLLMProvider(LLMProvider):
    name = "stub"
    model_name = "stub"

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        question = ""
        system = ""
        for message in reversed(messages):
            if message.role == "user":
                question = message.content
            elif message.role == "system":
                system = message.content
            if question and system:
                break

        system_lower = system.lower()
        if "generate study material" in system_lower:
            return json.dumps(_learning_payload())
        if "expand a knowledge graph" in system_lower:
            return json.dumps(_expand_payload())
        if "explain a concept" in system_lower:
            return json.dumps(_explain_payload())
        if "selection" in system_lower:
            return json.dumps(_selection_payload())
        if "knowledge graph" in system_lower:
            return json.dumps(_graph_payload())

        lowered = question.lower()
        payload: dict[str, Any]
        if any(marker in lowered for marker in _MARKERS["not_found"]):
            payload = {
                "answer": "I don't know from the provided sources.",
                "grounding": "not_found",
                "citations": [],
            }
        elif any(marker in lowered for marker in _MARKERS["inference"]):
            payload = {
                "answer": (
                    "Based on the evidence this appears to be an inference "
                    "rather than a stated fact."
                ),
                "grounding": "inference",
                "citations": [1],
            }
        else:
            payload = {
                "answer": "The answer is directly supported by the cited evidence.",
                "grounding": "supported_by_source",
                "citations": [1],
            }
        return json.dumps(payload)


def _graph_payload() -> dict[str, Any]:
    return {
        "concepts": [
            {
                "label": "Memory",
                "type": "concept",
                "definition": "The faculty for encoding, storing and retrieving information.",
            },
            {
                "label": "Consolidation",
                "type": "concept",
                "definition": "The process that stabilises memories over time.",
            },
            {
                "label": "Retrieval cues",
                "type": "concept",
                "definition": "Stimuli that improve recall accuracy.",
            },
            {
                "label": "Memory",
                "type": "concept",
                "definition": "Duplicate label to exercise deduplication.",
            },
            {
                "label": "Researchers",
                "type": "person",
                "definition": "People who ran the experiments.",
            },
        ],
        "relations": [
            {
                "source": "Consolidation",
                "target": "Memory",
                "relation": "AFFECTS",
                "note": "stabilises",
            },
            {
                "source": "Retrieval cues",
                "target": "Memory",
                "relation": "AFFECTS",
                "note": "improve recall",
            },
            {
                "source": "Consolidation",
                "target": "Memory",
                "relation": "AFFECTS",
                "note": "duplicate edge",
            },
        ],
    }


def _expand_payload() -> dict[str, Any]:
    return {
        "concepts": [
            {
                "label": "Slow-wave sleep",
                "type": "concept",
                "definition": "A sleep stage linked to consolidation.",
            },
            {
                "label": "Recall accuracy",
                "type": "concept",
                "definition": "A measure of retrieval performance.",
            },
            {
                "label": "Memory",
                "type": "concept",
                "definition": "Already present; must be merged, not duplicated.",
            },
        ],
        "relations": [
            {
                "source": "Slow-wave sleep",
                "target": "Consolidation",
                "relation": "SUPPORTS",
                "note": "hypothesis",
            },
            {
                "source": "Recall accuracy",
                "target": "Retrieval cues",
                "relation": "AFFECTS",
                "note": "measured in experiments",
            },
        ],
    }


def _explain_payload() -> dict[str, Any]:
    return {
        "explanation": (
            "The evidence describes memory as the faculty by which information "
            "is encoded, stored, and retrieved in the human brain."
        ),
        "grounding": "supported_by_source",
        "citations": [1],
    }


def _selection_payload() -> dict[str, Any]:
    return {
        "concepts": [
            {
                "label": "Working memory",
                "type": "concept",
                "definition": "The short-term store for active information.",
            },
            {
                "label": "Memory",
                "type": "concept",
                "definition": "Already present; must not be duplicated.",
            },
        ],
        "relations": [
            {
                "source": "Working memory",
                "target": "Memory",
                "relation": "PART_OF",
                "note": "component of",
            },
        ],
    }


def _learning_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "text": "Memory encodes, stores and retrieves information.",
                "term": "Memory",
                "question": "What is memory?",
                "answer": "The faculty for encoding, storing and retrieving information.",
                "front": "Memory",
                "back": "Encoding, storage and retrieval of information.",
                "options": ["Memory", "Sleep", "Cues"],
                "answer_index": 0,
                "section": "Foundations",
                "points": ["Encoding", "Storage", "Retrieval"],
            }
        ]
    }
