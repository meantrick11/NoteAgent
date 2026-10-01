"""Harness driving the real ConversationService against a real checkpointer.

The same class backs the fast in-memory suite and the PostgreSQL persistence suite,
so a test can be moved between them without changing anything but the fixture.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import Engine

from noteagent.chat.history import ConversationStore
from noteagent.conversations.checkpoints import (
    CheckpointRuntime,
    checkpoint_id_of,
)
from noteagent.conversations.records import (
    ConversationRecord,
    initial_state,
    ui_message_from_record,
    MessageRecord,
)
from noteagent.conversations.service import ConversationService
from noteagent.db import (
    Base,
    create_engine_from_url,
    create_session_factory,
    load_all_models,
)


def sqlalchemy_schema_url(database_url: str, schema: str) -> str:
    """Point a SQLAlchemy URL at one schema through libpq ``options``."""
    sep = "&" if "?" in database_url else "?"
    return f"{database_url}{sep}options=-csearch_path%3D{schema}"


class ConversationHarness:
    """Real service + real saver, over either SQLite/InMemory or PostgreSQL."""

    def __init__(self, *, sqlalchemy_url: str, libpq_dsn: str | None = None) -> None:
        self._sqlalchemy_url = sqlalchemy_url
        self._libpq_dsn = libpq_dsn
        self._engine: Engine | None = None
        self.runtime: CheckpointRuntime | None = None
        self.service: ConversationService | None = None
        self.history: ConversationStore | None = None

    @property
    def is_persistent(self) -> bool:
        """True when state survives :meth:`reopen`."""
        return self._libpq_dsn is not None

    async def start(self) -> "ConversationHarness":
        """Create tables and open the checkpointer."""
        load_all_models()
        self._engine = create_engine_from_url(self._sqlalchemy_url)
        Base.metadata.create_all(self._engine)
        if self._libpq_dsn is None:
            self.runtime = CheckpointRuntime.attached(InMemorySaver())
        else:
            self.runtime = CheckpointRuntime.from_conn_string(self._libpq_dsn)
        await self.runtime.open()
        factory = create_session_factory(self._engine)
        self.service = ConversationService(factory, self.runtime)
        self.history = ConversationStore(factory)
        return self

    async def close(self) -> None:
        """Release the saver connection and the engine."""
        if self.runtime is not None:
            await self.runtime.close()
        if self._engine is not None:
            self._engine.dispose()
        self.runtime = None
        self.service = None
        self.history = None

    async def reopen(self) -> "ConversationHarness":
        """Close everything and rebuild from the same database and schema."""
        await self.close()
        return await self.start()

    # -- operations under test ---------------------------------------------

    async def create_conversation(self, title: str = "test") -> ConversationRecord:
        assert self.service is not None
        return await self.service.create_conversation(title)

    def active_head(self, conversation_id: str) -> dict:
        assert self.service is not None
        return self.service.active_head_config(conversation_id)

    async def fork_unpublished(
        self, conversation_id: str, parent_config: dict
    ) -> dict:
        """Write a second checkpoint on the same thread without moving the app head."""
        assert self.service is not None
        branch_id = self.service.active_branch_id(conversation_id)
        values = dict(initial_state(branch_id=branch_id))
        values["ui_messages"] = [
            ui_message_from_record(
                MessageRecord(
                    id="abandoned-message",
                    conversation_id=conversation_id,
                    role="user",
                    content="abandoned branch",
                    created_at=_now(),
                    turn_id=None,
                    tool_name=None,
                    tool_arguments=None,
                    output_preview=None,
                    truncated=False,
                    status=None,
                )
            )
        ]
        return await self.service.write_state(
            conversation_id,
            values,
            branch_id=branch_id,
            parent_checkpoint_id=checkpoint_id_of(parent_config),
            publish=False,
        )


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
