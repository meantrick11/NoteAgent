"""Synchronous SQLAlchemy engine and session factory.

Used by the runtime (PostgreSQL) and unit tests (in-memory SQLite).
"""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_engine_from_url(url: str) -> Engine:
    """Create a synchronous engine from a SQLAlchemy URL string.

    SQLite URLs get ``check_same_thread=False`` and foreign-key enforcement;
    in-memory SQLite also shares one connection (StaticPool) so tables are
    visible across threads (e.g. TestClient). PostgreSQL URLs need neither.
    """
    if url.startswith("sqlite:"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)
        _enable_sqlite_foreign_keys(engine)
        return engine
    return create_engine(url)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Turn on SQLite FK enforcement for every new connection."""

    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", _set_sqlite_pragma)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a sessionmaker with expire_on_commit off and no autoflush."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
