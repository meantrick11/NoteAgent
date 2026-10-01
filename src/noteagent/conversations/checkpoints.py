"""Async checkpointer lifecycle and config adaptation.

The checkpointer is owned for the whole process lifetime (opened on lifespan startup,
closed on shutdown). Tests inject an ``InMemorySaver`` through :meth:`attach`; the
service code is identical either way.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any, AsyncContextManager, Mapping

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, empty_checkpoint
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

# Fixed application namespace: the thread id already identifies the conversation.
CHECKPOINT_NS = ""


def postgres_uri(database_url: str) -> str:
    """Convert a SQLAlchemy URL into the libpq URI psycopg needs.

    The credential stays inside the returned string and is never logged.
    """
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def thread_config(thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any]:
    """Build an explicit checkpoint config.

    Every read or write must name its checkpoint id when a specific state version is
    meant; the saver's "latest" is never a substitute for the active branch head.
    """
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "checkpoint_ns": CHECKPOINT_NS,
    }
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def checkpoint_id_of(config: Mapping[str, Any]) -> str | None:
    """Read the checkpoint id out of a config, or None when unpinned."""
    configurable = config.get("configurable") or {}
    return configurable.get("checkpoint_id")


def pinned(config: Mapping[str, Any], checkpoint_id: str) -> dict[str, Any]:
    """Copy a config, pinning it to one checkpoint id."""
    configurable = dict(config.get("configurable") or {})
    configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def state_to_checkpoint(
    values: Mapping[str, Any],
) -> tuple[Checkpoint, dict[str, Any]]:
    """Wrap plain state values as a checkpoint whose channels all carry its own version."""
    checkpoint = empty_checkpoint()
    data = dict(values)
    checkpoint["channel_values"] = data
    checkpoint["channel_versions"] = {key: checkpoint["id"] for key in data}
    checkpoint["updated_channels"] = list(data)
    return checkpoint, {key: checkpoint["id"] for key in data}


class CheckpointRuntime:
    """Owns the checkpointer object and, when it created it, its connection."""

    def __init__(self) -> None:
        self._saver: BaseCheckpointSaver | None = None
        self._context: AsyncContextManager[BaseCheckpointSaver] | None = None
        self._stack: AsyncExitStack | None = None

    @classmethod
    def from_conn_string(cls, uri: str) -> "CheckpointRuntime":
        """Runtime that will own an ``AsyncPostgresSaver`` over this libpq URI."""
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        runtime = cls()
        runtime._context = AsyncPostgresSaver.from_conn_string(uri)
        return runtime

    @classmethod
    def attached(cls, saver: BaseCheckpointSaver) -> "CheckpointRuntime":
        """Runtime around a saver the caller owns (tests use ``InMemorySaver``)."""
        runtime = cls()
        runtime._saver = saver
        return runtime

    @property
    def saver(self) -> BaseCheckpointSaver:
        """The open checkpointer; raises when the runtime was never opened."""
        if self._saver is None:
            raise RuntimeError("checkpointer is not open")
        return self._saver

    @property
    def is_open(self) -> bool:
        return self._saver is not None

    async def open(self) -> None:
        """Enter the saver context and run its one-time setup."""
        if self._saver is not None:
            return
        if self._context is None:
            raise RuntimeError("no saver or context to open")
        self._stack = AsyncExitStack()
        self._saver = await self._stack.enter_async_context(self._context)
        setup = getattr(self._saver, "setup", None)
        if callable(setup):
            await setup()
        logger.info("checkpoint runtime opened saver=%s", type(self._saver).__name__)

    async def close(self) -> None:
        """Release the connection. Safe to call when never opened."""
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._saver = None
            logger.info("checkpoint runtime closed")
