from mindweaver.config import RerankerConfig, SearchConfig, Settings
from mindweaver.search.base import SearchHit
from mindweaver.search.rerank import LocalReranker, get_reranker


def _hit(chunk_id: str, text: str, keyword: float, vector: float) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        document_id="doc_1",
        page_start=1,
        page_end=1,
        text=text,
        keyword_score=keyword,
        vector_score=vector,
        retrieval_score=0.0,
    )


def test_local_reranker_sorts_by_combined_score():
    reranker = LocalReranker()
    hits = [
        _hit("a", "memory consolidation", 0.2, 0.3),
        _hit("b", "memory consolidation", 0.8, 0.9),
    ]
    reranked = reranker.rerank("memory consolidation", hits)
    assert reranked[0].chunk_id == "b"
    assert all(hit.rerank_score is not None for hit in reranked)
    assert reranked[0].rerank_score > reranked[1].rerank_score


def test_overlap_boost_prefers_lexical_match():
    reranker = LocalReranker()
    hits = [
        _hit("a", "completely unrelated topic text", 0.0, 0.5),
        _hit("b", "consolidation stabilises memories during sleep", 0.0, 0.5),
    ]
    reranked = reranker.rerank("consolidation memories sleep", hits)
    assert reranked[0].chunk_id == "b"


def test_reranker_disabled_returns_none():
    settings = Settings(
        reranker=RerankerConfig(enabled=False),
        search=SearchConfig(fts_weight=0.5, vector_weight=0.5),
    )
    assert get_reranker(settings) is None


def test_reranker_enabled_default():
    assert get_reranker(Settings()) is not None
