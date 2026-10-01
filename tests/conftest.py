"""Shared fixtures for the checkpoint / shadow-git rollback suite.

Real production interfaces are reused wherever possible: fixtures provide
temporary paths, schema-isolated PostgreSQL databases, and deterministic
doubles. Nothing here skips silently — a missing PostgreSQL fails the test.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from sqlalchemy.engine import make_url

from noteagent.bootstrap.settings import Settings
from noteagent.notes.repository import FileNoteRepository
from support.fakes import FailInjector, FakeEmbedder


class _MaskedDsn(str):
    """A DSN string that never prints its password in test output or fixtures."""

    def __repr__(self) -> str:
        return "'<dsn>'"


def psycopg_dsn(sqlalchemy_url: str) -> _MaskedDsn:
    """Convert the app's SQLAlchemy URL into a libpq URI that psycopg accepts."""
    return _MaskedDsn(
        make_url(sqlalchemy_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def schema_dsn(dsn: str, schema: str) -> _MaskedDsn:
    """Pin one connection URI to a schema through ``search_path``."""
    sep = "&" if "?" in dsn else "?"
    return _MaskedDsn(f"{dsn}{sep}options=-csearch_path%3D{schema}")


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """libpq URI for the configured PostgreSQL; raises when unreachable."""
    settings = Settings()
    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL is required for PostgreSQL-backed tests")
    dsn = psycopg_dsn(settings.database_url)
    with psycopg.connect(dsn) as conn:
        conn.execute("select 1")
    return dsn


@pytest.fixture
def pg_schema(postgres_dsn: str):
    """Yield ``(name, dsn)`` for a throwaway schema, dropped afterwards."""
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(postgres_dsn, autocommit=True)
    admin.execute(f'create schema "{name}"')
    try:
        yield name, schema_dsn(postgres_dsn, name)
    finally:
        admin.execute(f'drop schema "{name}" cascade')
        admin.close()


@pytest.fixture
def tmp_notes(tmp_path):
    """A real FileNoteRepository rooted in a per-test temporary directory."""
    return FileNoteRepository(tmp_path / "notes")


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def fail_stage() -> FailInjector:
    return FailInjector()
