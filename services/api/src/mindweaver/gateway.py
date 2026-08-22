"""Model gateway (Stage 16).

Single access point for every AI capability. Business logic asks the gateway
for a provider; nothing imports concrete provider modules directly. The same
contract tests run against every registered implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from mindweaver.config import Settings

if TYPE_CHECKING:
    from mindweaver.extraction.base import DocumentProcessor
    from mindweaver.llm.base import LLMProvider
    from mindweaver.search.embeddings.base import EmbeddingProvider
    from mindweaver.search.rerank import Reranker


@dataclass
class ModelGateway:
    """Aggregates all interchangeable providers resolved from settings."""

    settings: Settings

    @cached_property
    def llm(self) -> LLMProvider:
        from mindweaver.llm.registry import get_llm_provider

        return get_llm_provider(self.settings)

    @cached_property
    def embeddings(self) -> EmbeddingProvider | None:
        from mindweaver.search.embeddings.registry import get_embedding_provider

        return get_embedding_provider(self.settings)

    @cached_property
    def reranker(self) -> Reranker | None:
        from mindweaver.search.rerank import get_reranker

        return get_reranker(self.settings)

    @cached_property
    def document_processor(self) -> DocumentProcessor:
        from mindweaver.extraction.registry import get_processor

        return get_processor(self.settings, session=None, ocr_enabled=False)


def build_gateway(settings: Settings) -> ModelGateway:
    return ModelGateway(settings=settings)


def provider_status(settings: Settings) -> list[dict[str, str | None]]:
    """Provider inventory for the /models status endpoint."""
    status: list[dict[str, str | None]] = []

    try:
        gateway = build_gateway(settings)
        status.append(
            {"capability": "llm", "provider": gateway.llm.name, "model": gateway.llm.model_name}
        )
        if gateway.embeddings is not None:
            status.append(
                {
                    "capability": "embeddings",
                    "provider": gateway.embeddings.name,
                    "model": gateway.embeddings.model_name,
                }
            )
        else:
            status.append({"capability": "embeddings", "provider": None, "model": None})
        status.append(
            {
                "capability": "reranker",
                "provider": gateway.reranker.name if gateway.reranker else None,
                "model": settings.reranker.model or ("local" if gateway.reranker else None),
            }
        )
        status.append(
            {
                "capability": "document_processor",
                "provider": gateway.document_processor.name,
                "model": None,
            }
        )
    except Exception as exc:
        status.append({"capability": "error", "provider": str(exc), "model": None})
    try:
        from mindweaver.ocr.registry import get_ocr_provider

        ocr = get_ocr_provider(settings)
        status.append({"capability": "ocr", "provider": ocr.name, "model": None})
    except Exception:
        status.append({"capability": "ocr", "provider": None, "model": None})

    return status
