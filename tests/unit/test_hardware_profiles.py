"""Stage 20: hardware profiles tune provider/config presets."""

from mindweaver.config import Settings


def test_low_profile_disables_reranker_and_slims_down():
    settings = Settings(hardware_profile="low")
    assert settings.reranker.enabled is False
    assert settings.embeddings.provider == "local"
    assert settings.embeddings.dimension <= 256
    assert settings.search.fts_weight > settings.search.vector_weight
    assert settings.worker.concurrency == 1
    assert settings.chat.evidence_limit <= 4


def test_high_profile_prefers_quality():
    settings = Settings(hardware_profile="high")
    assert settings.embeddings.provider == "sentence-transformers"
    assert settings.document_processor.backend == "docling"
    assert settings.chat.evidence_limit >= 8


def test_medium_profile_is_default():
    settings = Settings()
    assert settings.hardware_profile == "medium"
    # medium keeps defaults untouched (reranker on, local embeddings)
    assert settings.reranker.enabled is True
