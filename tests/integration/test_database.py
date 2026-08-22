import pytest
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError


def test_database_initializes_and_answers_queries(tmp_path):
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/data.db"))
    engine = build_engine(settings)
    init_database(engine)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        result = session.execute(text("SELECT 1")).scalar_one()
    assert result == 1

    tables = inspect(engine).get_table_names()
    assert "documents" in tables
    assert "document_versions" in tables
    assert "processing_jobs" in tables


def test_database_creates_missing_parent_directory(tmp_path):
    target = tmp_path / "nested" / "dir" / "data.db"
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{target}"))
    engine = build_engine(settings)
    init_database(engine)
    assert target.exists()


def test_session_scope_rolls_back_on_error(tmp_path):
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/rollback.db"))
    engine = build_engine(settings)
    init_database(engine)
    factory = make_session_factory(engine)

    with pytest.raises(OperationalError), session_scope(factory) as session:
        session.execute(text("SELECT * FROM missing_table"))
