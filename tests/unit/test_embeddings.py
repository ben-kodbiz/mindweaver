import math

from mindweaver.config import Settings
from mindweaver.search.embeddings.hashing import HashingEmbeddingProvider
from mindweaver.search.embeddings.registry import get_embedding_provider


def test_hashing_provider_shape_and_norm():
    provider = HashingEmbeddingProvider(dimension=64)
    assert provider.dimension == 64
    vectors = provider.embed(["hello world", "another text"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 64
    norm = math.sqrt(sum(v * v for v in vectors[0]))
    assert abs(norm - 1.0) < 1e-6


def test_hashing_provider_deterministic():
    provider = HashingEmbeddingProvider(dimension=128)
    assert provider.embed(["same text"]) == provider.embed(["same text"])


def test_similar_texts_are_closer():
    provider = HashingEmbeddingProvider(dimension=256)
    query = provider.embed(["memory consolidation during sleep"])[0]
    similar = provider.embed(["memory consolidation during sleep"])[0]
    different = provider.embed(["quantum physics of stars"])[0]
    dot_similar = sum(a * b for a, b in zip(query, similar, strict=True))
    dot_different = sum(a * b for a, b in zip(query, different, strict=True))
    assert dot_similar > dot_different


def test_registry_default_is_local():
    provider = get_embedding_provider(Settings())
    assert provider is not None
    assert provider.name == "local"


def test_registry_none_disables():
    settings = Settings.model_construct()
    settings.embeddings.provider = "none"
    assert get_embedding_provider(settings) is None


def test_sentence_transformer_provider():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("embeddings extra not installed")
    from mindweaver.search.embeddings.sentence_transformer import SentenceTransformerProvider

    provider = SentenceTransformerProvider(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    vectors = provider.embed(["memory consolidation during sleep", "quantum physics of stars"])
    assert len(vectors) == 2
    assert all(len(v) == provider.dimension for v in vectors)
    # similar sentence should be closer than unrelated one
    sim = sum(a * b for a, b in zip(vectors[0], vectors[0], strict=True))
    diff = sum(a * b for a, b in zip(vectors[0], vectors[1], strict=True))
    assert sim > diff
