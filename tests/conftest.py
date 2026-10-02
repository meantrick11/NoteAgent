"""Shared fixtures for the checkpoint / shadow-git rollback suite.

Real production interfaces are reused wherever possible: fixtures provide
temporary paths, schema-isolated PostgreSQL databases, and deterministic
doubles. Nothing here skips silently — a missing PostgreSQL fails the test.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass

import psycopg
import pytest

from noteagent.bootstrap.settings import Settings
from noteagent.conversations.checkpoints import postgres_uri
from noteagent.notes.repository import FileNoteRepository
from support.fakes import FailInjector, FakeChatModel, FakeEmbedder
from support.harness import ConversationHarness, sqlalchemy_schema_url

# psycopg's async driver refuses Windows' default ProactorEventLoop; the production
# image runs on Linux, so this only affects the local test process.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class _MaskedDsn(str):
    """A DSN string that never prints its password in test output or fixtures."""

    def __repr__(self) -> str:
        return "'<dsn>'"


@dataclass
class PgTarget:
    """A throwaway schema plus both URL forms needed to reach it."""

    name: str
    sqlalchemy_url: str
    libpq_dsn: str

    def __repr__(self) -> str:  # never leak the credential into failure output
        return f"PgTarget(name={self.name!r})"


def psycopg_dsn(sqlalchemy_url: str) -> _MaskedDsn:
    """Convert the app's SQLAlchemy URL into a libpq URI that psycopg accepts."""
    return _MaskedDsn(postgres_uri(sqlalchemy_url))


def _settings() -> Settings:
    settings = Settings()
    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL is required for PostgreSQL-backed tests")
    return settings


@pytest.fixture(scope="session")
def postgres_dsn() -> _MaskedDsn:
    """libpq URI for the configured PostgreSQL; raises when unreachable."""
    dsn = psycopg_dsn(_settings().database_url)
    with psycopg.connect(dsn) as conn:
        conn.execute("select 1")
    return dsn


@pytest.fixture
def pg_target(postgres_dsn: str) -> PgTarget:
    """Yield a throwaway schema, dropped after the test."""
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(postgres_dsn, autocommit=True)
    admin.execute(f'create schema "{name}"')
    try:
        yield PgTarget(
            name=name,
            sqlalchemy_url=sqlalchemy_schema_url(_settings().database_url, name),
            libpq_dsn=schema_dsn(postgres_dsn, name),
        )
    finally:
        admin.execute(f'drop schema "{name}" cascade')
        admin.close()


def schema_dsn(dsn: str, schema: str) -> _MaskedDsn:
    """Pin one libpq URI to a schema through ``search_path``."""
    sep = "&" if "?" in dsn else "?"
    return _MaskedDsn(f"{dsn}{sep}options=-csearch_path%3D{schema}")


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


async def _run_harness(harness: ConversationHarness):
    """Start a harness, hand it to the test, and always release it."""
    await harness.start()
    try:
        yield harness
    finally:
        await harness.close()


@pytest.fixture
async def conversation_harness(tmp_notes):
    """In-memory checkpointer over SQLite, with a scripted model and real tools.

    Nothing survives reopen, so persistence is exercised by ``postgres_harness``.
    """
    harness = ConversationHarness(
        sqlalchemy_url="sqlite:///:memory:",
        notes=tmp_notes,
        model=FakeChatModel([]),
    )
    async for started in _run_harness(harness):
        yield started


@pytest.fixture
async def postgres_harness(pg_target: PgTarget, tmp_notes):
    """Real PostgreSQL schema and real AsyncPostgresSaver; survives reopen."""
    harness = ConversationHarness(
        sqlalchemy_url=pg_target.sqlalchemy_url,
        libpq_dsn=pg_target.libpq_dsn,
        notes=tmp_notes,
        model=FakeChatModel([]),
    )
    async for started in _run_harness(harness):
        yield started
