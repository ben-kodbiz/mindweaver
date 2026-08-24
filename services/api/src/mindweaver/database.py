"""SQLAlchemy engine/session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Boolean, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mindweaver.config import Settings
from mindweaver.models.base import Base


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(settings: Settings) -> Engine:
    url = settings.database.url
    kwargs: dict[str, object] = {"echo": settings.database.echo}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


def _migrate_missing_columns(engine: Engine) -> None:
    """SQLite create_all does not alter existing tables; add any columns that
    the models gained since the table was first created."""
    from sqlalchemy import inspect as sa_inspect

    from mindweaver import models as _models  # noqa: F401  (registers tables)

    inspector = sa_inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(engine.dialect)
            clause = f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'
            if not column.nullable:
                # SQLite requires a DEFAULT for NOT NULL columns on existing rows.
                if isinstance(column.type, Boolean):
                    clause += " NOT NULL DEFAULT 0"
                else:
                    clause += " NOT NULL DEFAULT ''"
            with engine.begin() as conn:
                conn.execute(text(clause))


def init_database(engine: Engine) -> None:
    from mindweaver import models as _models  # noqa: F401  (registers tables)

    if engine.url.drivername.startswith("sqlite"):
        database = engine.url.database
        if database not in (None, "", ":memory:"):
            Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate_missing_columns(engine)
    from mindweaver.search.fts import ensure_fts

    ensure_fts(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
