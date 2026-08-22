"""Stages 5-7: expansion proposals, orchestrator, intelligence API."""

from mindweaver.intelligence.config import IntelligenceConfig
from mindweaver.intelligence.expansion import validate_children
from mindweaver.intelligence.orchestrator import OrchestratorLimits, run_orchestrator_with_context

# --- proposal validation (Stage 5) -----------------------------------------


def _config(**kw):
    return IntelligenceConfig(node_expansion={"enabled": True, **kw})


VALID_CHUNKS = {"chunk_100", "chunk_200"}


def test_valid_children_accepted():
    children, warnings = validate_children(
        [
            {
                "label": "Cause A",
                "relationship": "causes",
                "evidence": [{"chunk_id": "chunk_100", "page_number": 5}],
            },
        ],
        valid_chunk_ids=VALID_CHUNK_IDS,
        existing_labels=set(),
        config=_config(),
    )
    assert len(children) == 1 and not warnings


def test_child_without_label_rejected():
    _, warnings = validate_children(
        [{"label": "", "evidence": [{"chunk_id": "chunk_100"}]}],
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels=set(),
        config=_config(),
    )
    assert any("without a label" in w for w in warnings)


def test_child_without_evidence_rejected_when_required():
    _, warnings = validate_children(
        [{"label": "No Evidence", "evidence": []}],
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels=set(),
        config=_config(),
    )
    assert any("no valid evidence" in w for w in warnings)


def test_invalid_chunk_id_rejected():
    _, warnings = validate_children(
        [{"label": "Bad", "evidence": [{"chunk_id": "fake_chunk"}]}],
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels=set(),
        config=_config(),
    )
    assert any("no valid evidence" in w for w in warnings)


def test_duplicate_label_rejected():
    _, warnings = validate_children(
        [
            {"label": "Same", "evidence": [{"chunk_id": "chunk_100"}]},
            {"label": "Same", "evidence": [{"chunk_id": "chunk_200"}]},
        ],
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels=set(),
        config=_config(),
    )
    assert any("duplicate" in w for w in warnings)


def test_existing_graph_label_treated_as_duplicate():
    _, warnings = validate_children(
        [{"label": "Memory", "evidence": [{"chunk_id": "chunk_100"}]}],
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels={"memory"},
        config=_config(),
    )
    assert any("duplicate" in w for w in warnings)


def test_max_children_enforced():
    items = [{"label": f"N{i}", "evidence": [{"chunk_id": "chunk_100"}]} for i in range(20)]
    children, warnings = validate_children(
        items,
        valid_chunk_ids=VALID_CHUNKS,
        existing_labels=set(),
        config=_config(max_children=3),
    )
    assert len(children) == 3


VALID_CHUNK_IDS = VALID_CHUNKS


# --- Stage 6: orchestrator limits -------------------------------------------


class _FakeModel:
    """Returns queued responses one at a time."""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.capabilities = type(
            "Caps",
            (),
            {
                "chat": True,
                "tool_calling": True,
                "structured_output": True,
                "vision": False,
            },
        )()

    def chat_with_tools(self, messages, tools, **options):
        if not self._responses:
            raise RuntimeError("no more canned responses")
        payload = self._responses.pop(0)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        message = {"role": "assistant", "content": payload.get("content")}
        if payload.get("tool_calls"):
            message["tool_calls"] = payload["tool_calls"]
        return type(
            "R",
            (),
            {
                "content": message["content"],
                "has_tool_calls": bool(payload.get("tool_calls")),
                "tool_calls": [
                    type(
                        "TC",
                        (),
                        {
                            "id": tc.get("id", ""),
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    )()
                    for tc in (payload.get("tool_calls") or [])
                ],
                "finish_reason": None,
            },
        )()


class _EmptyRegistry:
    def specs(self):
        return []

    def execute(self, ctx, name, args, **kw):
        from mindweaver.intelligence.tools.registry import ToolResult

        return ToolResult(name=name, ok=False, error="no tools")


class _Ctx:
    document_ids = ("doc_1",)
    session = None
    settings = None


def test_orchestrator_final_answer_no_tools():
    model = _FakeModel([{"content": "the answer"}])
    result = run_orchestrator_with_context(
        model, _EmptyRegistry(), _Ctx(), [], OrchestratorLimits()
    )
    assert result.final_text == "the answer"
    assert result.tool_calls_made == 0


def test_orchestrator_iteration_limit():
    responses = [
        {
            "tool_calls": [
                {"id": str(i), "type": "function", "function": {"name": "t", "arguments": "{}"}}
            ]
        }
        for i in range(10)
    ]
    model = _FakeModel(responses)
    result = run_orchestrator_with_context(
        model, _EmptyRegistry(), _Ctx(), [], OrchestratorLimits(max_iterations=3)
    )
    assert result.stopped_reason == "iteration_limit"
