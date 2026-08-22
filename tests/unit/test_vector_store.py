from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.search.vector import (
    delete_embeddings,
    store_embedding,
    vector_search,
)
from sqlalchemy.orm import Session


def _settings(tmp_path) -> Settings:
    return Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/v.db"))


def _store(session: Session, chunk_id: str, vector: list[float]) -> None:
    store_embedding(
        session,
        chunk_id=chunk_id,
        document_id="doc_1",
        model_name="test-model",
        dimension=len(vector),
        vector=vector,
    )


def test_vector_search_returns_most_similar_first(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        _store(session, "a", [1.0, 0.0])
        _store(session, "b", [0.9, 0.1])
        _store(session, "c", [0.0, 1.0])
        session.flush()
        hits = vector_search(session, [1.0, 0.0], "test-model", limit=2)
    assert [h["chunk_id"] for h in hits] == ["a", "b"]
    assert hits[0]["score"] > hits[1]["score"]


def test_vector_search_respects_limit(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        for i in range(5):
            _store(session, f"chunk_{i}", [float(i), 0.0])
        session.commit()
        hits = vector_search(session, [1.0, 0.0], "test-model", limit=3)
    assert len(hits) == 3


def test_delete_embeddings(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        _store(session, "a", [1.0, 0.0])
        session.commit()
        delete_embeddings(session, "doc_1", "test-model")
        session.commit()
        hits = vector_search(session, [1.0, 0.0], "test-model")
    assert hits == []


def test_zero_norm_query_returns_nothing(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with make_session_factory(engine)() as session:
        _store(session, "a", [1.0, 0.0])
        session.commit()
        hits = vector_search(session, [0.0, 0.0], "test-model")
    assert hits == []
