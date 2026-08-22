"""Stage 5: evidence-based mind-map expansion proposals.

The model proposes child nodes; the application validates every proposal
against the stored evidence. Nothing is committed automatically — the caller
reviews the proposal and explicitly accepts (via the personal-layer API) or
rejects it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from mindweaver.chunking.service import list_chunks
from mindweaver.config import Settings
from mindweaver.graph.service import get_graph
from mindweaver.intelligence.config import IntelligenceConfig
from mindweaver.intelligence.orchestrator import (
    OrchestratorLimits,
    run_orchestrator_with_context,
)
from mindweaver.intelligence.tools.registry import ToolRegistry
from mindweaver.models import Document

logger = logging.getLogger("intelligence.proposal")


class ExpansionError(Exception):
    pass


@dataclass
class ExpansionChild:
    label: str
    relationship: str
    description: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExpansionProposal:
    node_id: str
    children: list[ExpansionChild] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "children": [
                {
                    "label": c.label,
                    "relationship": c.relationship,
                    "description": c.description,
                    "evidence": c.evidence,
                }
                for c in self.children
            ],
            "warnings": self.warnings,
        }


SYSTEM_PROMPT = """You expand a knowledge-graph node for the user's document.
You may request evidence with the provided tools before answering.
When ready, respond ONLY with JSON:
{"children": [{"label": "...", "relationship": "...",
               "description": "...",
               "evidence": [{"chunk_id": "...", "page_number": 1}]}]}
Every child MUST cite at least one chunk that actually exists in this document.
Do not invent chunk ids."""


# --- validation ------------------------------------------------------------


def validate_children(
    raw_items: list[dict[str, Any]],
    *,
    valid_chunk_ids: set[str],
    existing_labels: set[str],
    config: IntelligenceConfig,
) -> tuple[list[ExpansionChild], list[str]]:
    warnings: list[str] = []
    accepted: list[ExpansionChild] = []
    seen_labels: set[str] = set()

    max_children = config.node_expansion.max_children
    require_evidence = config.node_expansion.require_evidence

    for item in raw_items[:max_children]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            warnings.append("rejected child without a label")
            continue
        key = label.lower()
        if key in seen_labels or key in existing_labels:
            warnings.append(f"duplicate child '{label}' rejected")
            continue
        seen_labels.add(key)

        evidence = [
            e
            for e in item.get("evidence") or []
            if isinstance(e, dict) and str(e.get("chunk_id")) in valid_chunk_ids
        ]
        if require_evidence and not evidence:
            warnings.append(f"child '{label}' rejected: no valid evidence")
            continue

        accepted.append(
            ExpansionChild(
                label=label,
                relationship=str(item.get("relationship") or "related"),
                description=str(item.get("description") or "")[:500],
                evidence=[
                    {"chunk_id": e["chunk_id"], "page_number": int(e.get("page_number", 0))}
                    for e in evidence
                ],
            )
        )

    overflow = len(raw_items) - max_children
    if overflow > 0:
        warnings.append(f"{overflow} children dropped: max_children={max_children}")
    return accepted, warnings


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


# --- expansion -------------------------------------------------------------


def propose_with_gateway(
    session: Session,
    settings: Settings,
    intel_config: IntelligenceConfig,
    gateway: Any,
    document: Document,
    node_id: str,
) -> ExpansionProposal:
    """Tool-using expansion: the model gathers evidence via registered tools,
    then proposes children which are validated against real chunk ids."""
    from mindweaver.intelligence.tools.builtin import register_builtin_tools

    graph = get_graph(session, document.id)
    if graph is None:
        raise ExpansionError("graph not available; process the document first")
    node = next((n for n in graph.nodes if n.id == node_id), None)
    if node is None:
        raise ExpansionError(f"node not found: {node_id}")

    chunks = list_chunks(session, document.id)
    valid_chunk_ids = {c.chunk_id for c in chunks}
    existing_labels = {n.label.lower() for n in graph.nodes}

    registry = ToolRegistry()
    register_builtin_tools(registry)

    from types import SimpleNamespace

    tool_context = SimpleNamespace(
        session=session,
        settings=settings,
        document_ids=(document.id,),
    )

    limits = OrchestratorLimits(
        max_iterations=intel_config.tools.max_iterations,
        max_tool_calls=intel_config.tools.max_tool_calls,
        timeout_seconds=intel_config.tools.timeout_seconds,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Expand the node '{node.label}' (type {node.type.value}) "
                f"for document '{document.title}'."
            ),
        },
    ]
    outcome = run_orchestrator_with_context(gateway.text, registry, tool_context, messages, limits)

    payload = extract_json_object(outcome.final_text or "")
    if payload is None:
        raise ExpansionError(f"model did not produce a valid proposal ({outcome.stopped_reason})")

    raw_children = payload.get("children") or []
    if not isinstance(raw_children, list):
        raise ExpansionError("proposal 'children' must be a list")

    children, warnings = validate_children(
        raw_children,
        valid_chunk_ids=valid_chunk_ids,
        existing_labels=existing_labels,
        config=intel_config,
    )
    logger.info(
        "intelligence.proposal.created node=%s children=%d warnings=%d",
        node_id,
        len(children),
        len(warnings),
    )
    return ExpansionProposal(
        node_id=node_id,
        children=children,
        warnings=warnings,
        tool_log=outcome.tool_log,
    )
