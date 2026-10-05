"""Legacy conversation import into the checkpoint backend.

The legacy ``messages`` table stays the source of truth until a conversation is
imported; import writes a candidate checkpoint, verifies it against the legacy
rows, and only then CAS-switches ``state_backend``. These cases run on a real
PostgreSQL schema and must not touch any real user notes.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from NoteAgent.TechnicalSupport.DatabaseAccess import create_session_factory
from NoteAgent.BusinessModules.ConversationState.ConversationModels import Conversation
from NoteAgent.BusinessModules.ConversationState.LegacyConversationCompatibility.LegacyConversationMigration import HISTORY_NOT_RECOVERABLE, ConversationMigrator
from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationBranch, UserMessageBoundary


def _migrator(harness) -> ConversationMigrator:
    """A migrator over the harness engine, reusing its real service and legacy store."""
    factory = create_session_factory(harness._engine)
    return ConversationMigrator(factory, harness.service, legacy=harness.history)


def _seed(h, title: str = "Legacy chat"):
    """A legacy conversation with tools, citations, a summary watermark and a draft."""
    conv = h.history.create(title)
    first = str(uuid.uuid4())
    h.history.append_message(conv.id, "user", "第一条问题", turn_id=first)
    h.history.append_tool_stub(
        conv.id, turn_id=first, tool_name="search_notes",
        arguments='{"query":"alpha"}', output="命中一段很长的工具输出", status="ok",
        stub_preview_tokens=5, args_preview_chars=12,
    )
    h.history.append_message(
        conv.id, "assistant", "第一条回答", turn_id=first,
        citations=[{"index": 1, "path": "a.md", "heading": "A"}],
    )
    second = str(uuid.uuid4())
    h.history.append_message(conv.id, "user", "第二条问题", turn_id=second)
    h.history.append_message(conv.id, "assistant", "第二条回答", turn_id=second)
    h.history.apply_compact(conv.id, summary_append="阶段摘要", watermark_turn_id=first)
    h.history.set_pending_draft(
        conv.id, {"action": "create", "file_name": "n.md", "content": "draft body"}
    )
    return conv, first, second


def _state_backend(harness, conversation_id: str) -> str | None:
    with create_session_factory(harness._engine)() as session:
        return session.scalar(
            select(Conversation.state_backend).where(
                Conversation.id == uuid.UUID(conversation_id)
            )
        )


@pytest.mark.asyncio
async def test_import_preserves_messages_summary_draft_and_citations(postgres_harness):
    h = postgres_harness
    conv, watermark, _ = _seed(h)
    migrator = _migrator(h)

    legacy = h.history.list_messages(conv.id)
    assert legacy is not None

    report = await migrator.import_all(batch_id="batch-1")

    assert report.imported == 1
    assert report.errors == []

    view = await h.service.get_state(conv.id)
    values = view.values
    ui = values["ui_messages"]
    assert [m["role"] for m in ui] == ["user", "assistant", "user", "assistant"]
    # Original ids and timestamps survive the import.
    assert [m["id"] for m in ui] == [r.id for r in legacy]
    assert [m["content"] for m in ui] == [r.content for r in legacy]
    assert [m["created_at"] for m in ui] == [
        r.created_at.isoformat() for r in legacy
    ]
    # Citations and tool steps are attached to the matching assistant bubble.
    assert ui[1]["citations"] == [{"index": 1, "path": "a.md", "heading": "A"}]
    assert ui[1]["tool_steps"][0]["name"] == "search_notes"
    # Summary watermark and draft are carried over.
    assert values["running_summary"] == "阶段摘要"
    assert values["summary_watermark_turn_id"] == watermark
    assert values["pending_draft"]["file_name"] == "n.md"
    # Only records after the watermark stay in the model window.
    assert [m["content"] for m in values["working_records"]] == ["第二条问题", "第二条回答"]
    # Import never invents a note version.
    assert values["notes_commit"] is None
    assert _state_backend(h, conv.id) == "checkpoint"

    with create_session_factory(h._engine)() as session:
        branch = session.scalar(
            select(ConversationBranch).where(
                ConversationBranch.conversation_id == uuid.UUID(conv.id)
            )
        )
        assert branch is not None and branch.head_checkpoint_id is not None


@pytest.mark.asyncio
async def test_imported_history_is_not_falsely_editable(postgres_harness):
    h = postgres_harness
    conv, _, _ = _seed(h)
    migrator = _migrator(h)
    await migrator.import_all(batch_id="batch-1")

    records = await h.service.list_messages(conv.id)
    assert records is not None
    users = [r for r in records if r.role == "user"]
    assert users
    assert all(r.edit_unavailable_reason == HISTORY_NOT_RECOVERABLE for r in users)

    with create_session_factory(h._engine)() as session:
        boundaries = session.scalar(
            select(func.count()).select_from(UserMessageBoundary).where(
                UserMessageBoundary.conversation_id == uuid.UUID(conv.id)
            )
        )
    # Imported messages have no safe boundary, so they can never be forked from.
    assert boundaries == 0


@pytest.mark.asyncio
async def test_import_retry_does_not_duplicate_messages(postgres_harness):
    h = postgres_harness
    conv, _, _ = _seed(h)
    migrator = _migrator(h)

    first = await migrator.import_all(batch_id="batch-1")
    assert first.imported == 1
    head_after_first = h.active_head(conv.id)
    ids_after_first = [m["id"] for m in (await h.service.get_state(conv.id)).values["ui_messages"]]

    second = await migrator.import_all(batch_id="batch-2")
    assert second.imported == 0
    assert second.already_imported == 1

    head_after_second = h.active_head(conv.id)
    ids_after_second = [m["id"] for m in (await h.service.get_state(conv.id)).values["ui_messages"]]
    assert head_after_first == head_after_second
    assert ids_after_first == ids_after_second

    with create_session_factory(h._engine)() as session:
        rows = session.scalar(
            select(func.count()).select_from(Conversation).where(
                Conversation.id == uuid.UUID(conv.id)
            )
        )
    assert rows == 1


@pytest.mark.asyncio
async def test_failed_import_leaves_legacy_rows_and_retries_cleanly(
    postgres_harness, monkeypatch
):
    h = postgres_harness
    conv, _, _ = _seed(h)
    migrator = _migrator(h)

    original = h.service.write_state
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected saver failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(h.service, "write_state", flaky)

    failed = await migrator.import_all(batch_id="batch-1")
    assert failed.failed == 1
    assert failed.imported == 0
    # Nothing was published: the conversation is still legacy and head-less.
    assert _state_backend(h, conv.id) == "legacy"

    retried = await migrator.import_all(batch_id="batch-1")
    assert retried.imported == 1
    legacy = h.history.list_messages(conv.id)
    ui = (await h.service.get_state(conv.id)).values["ui_messages"]
    assert [m["id"] for m in ui] == [r.id for r in legacy]


@pytest.mark.asyncio
async def test_dry_run_reports_counts_without_writing(postgres_harness):
    h = postgres_harness
    conv, _, _ = _seed(h)
    migrator = _migrator(h)

    report = migrator.dry_run()

    assert report.scanned == 1
    assert report.importable == 1
    assert report.imported == 0
    assert report.messages == 5
    assert report.errors == []
    # Dry-run never moves the backend.
    assert _state_backend(h, conv.id) == "legacy"


@pytest.mark.asyncio
async def test_cli_apply_twice_matches_ids_and_head(postgres_harness):
    from NoteAgent.AppBootstrap.AppSettings import Settings
    from Scripts.MigrateConversations import run

    h = postgres_harness
    conv, _, _ = _seed(h)
    settings = Settings(database_url=h._sqlalchemy_url)

    first = await run(["--apply"], settings=settings)
    assert first["imported"] == 1
    head_after_first = h.active_head(conv.id)
    ids_after_first = [m["id"] for m in (await h.service.get_state(conv.id)).values["ui_messages"]]

    second = await run(["--apply"], settings=settings)
    assert second["imported"] == 0
    assert h.active_head(conv.id) == head_after_first
    ids_after_second = [m["id"] for m in (await h.service.get_state(conv.id)).values["ui_messages"]]
    assert ids_after_second == ids_after_first
