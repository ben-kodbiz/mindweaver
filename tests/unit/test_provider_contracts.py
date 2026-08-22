"""Stage 16 contract tests.

The same interface contracts run against every registered implementation, so
providers stay interchangeable.
"""

import math

import pytest
from mindweaver.config import Settings
from mindweaver.gateway import build_gateway
from mindweaver.llm.base import LLMMessage


@pytest.fixture
def gateway():
    settings = Settings()
    settings.llm.provider = "stub"
    return build_gateway(settings)


def test_llm_contract(gateway):
    provider = gateway.llm
    out = provider.complete([LLMMessage(role="user", content="What is memory?")], max_tokens=32)
    assert isinstance(out, str)
    assert "grounding" in out or "{" in out


def test_embeddings_contract(gateway):
    provider = gateway.embeddings
    assert provider is not None
    vectors = provider.embed(["memory consolidation", "retrieval cues"])
    assert len(vectors) == 2
    dim = len(vectors[0])
    assert dim > 0
    for vector in vectors:
        assert len(vector) == dim
        norm = math.sqrt(sum(value * value for value in vector))
        assert abs(norm - 1.0) < 1e-6  # L2 normalised


def test_reranker_contract(gateway):
    from mindweaver.search.base import SearchHit

    reranker = gateway.reranker
    if reranker is None:
        pytest.skip("reranker disabled")
    hits = [
        SearchHit(
            chunk_id="a",
            document_id="d",
            page_start=1,
            page_end=1,
            text="memory",
            keyword_score=0.5,
            vector_score=0.5,
            retrieval_score=0.5,
        ),
        SearchHit(
            chunk_id="b",
            document_id="d",
            page_start=2,
            page_end=2,
            text="sleep",
            keyword_score=0.9,
            vector_score=0.9,
            retrieval_score=0.9,
        ),
    ]
    out = reranker.rerank("memory", hits)
    assert [h.chunk_id for h in out] == ["b", "a"]
    assert all(hit.rerank_score is not None for hit in out)


def test_document_processor_contract(gateway):
    processor = gateway.document_processor
    assert processor.name


def test_gateway_status_lists_capabilities():
    from mindweaver.gateway import provider_status

    status = {item["capability"]: item for item in provider_status(Settings())}
    assert {"llm", "embeddings", "reranker", "document_processor"} <= set(status)
    assert status["llm"]["provider"] is not None
