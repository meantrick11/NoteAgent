"""Recovery coordinator: staged restore, idempotency, maintenance and conflicts."""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from noteagent.conversations.checkpoints import CheckpointRuntime, checkpoint_id_of
from noteagent.conversations.service import ConversationService
from noteagent.db import Base, create_engine_from_url, create_session_factory, load_all_models
from noteagent.notes.mutations import CREATE, WRITE, MutationCommand, NoteMutationService, Origin
from noteagent.notes.repository import FileNoteRepository
from noteagent.notes.versions import NoteVersionStore
from noteagent.recovery.gate import WorkspaceBusy, WorkspaceGate
from noteagent.recovery.models import RecoveryJob
from noteagent.recovery.service import (
    ConfirmationRequired,
    PlanConflict,
    RecoveryCoordinator,
)
from noteagent.retrieval.repairs import IndexRepairService
from support.fakes import FailInjector


class _FakeRetrieval:
    def __init__(self) -> None:
        self.model_name = "fake"
        self.indexed: set[str] = set()

    def config_fingerprint(self) -> str:
        return "fake-fp"

    def is_indexed(self, name: str) -> bool:
        return name in self.indexed

    def index_note(self, name: str) -> int:
        self.indexed.add(name)
        return 1

    def delete_note(self, name: str) -> None:
        self.indexed.discard(name)

    def search(self, query: str, top_k: int = 3):
        return []


class _Env:
    def __init__(self, tmp_path, faults=None):
        self.notes = FileNoteRepository(tmp_path / "notes")
        self.versions = NoteVersionStore(tmp_path / "history", self.notes.root)
        load_all_models()
        engine = create_engine_from_url("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.factory = create_session_factory(engine)
        self.gate = WorkspaceGate(self.factory)
        self.gate.ensure_row()
        self.checkpoints = CheckpointRuntime.attached(InMemorySaver())
        self.conversations = ConversationService(
            self.factory, self.checkpoints,
            workspace_seq_provider=lambda: self.gate.state().seq,
        )
        self.retrieval = _FakeRetrieval()
        self.repairs = IndexRepairService(self.factory, self.notes)
        self.mutations = NoteMutationService(
            self.notes, self.versions, self.gate, self.factory, repairs=self.repairs
        )
        self.coordinator = RecoveryCoordinator(
            session_factory=self.factory, gate=self.gate, conversations=self.conversations,
            mutations=self.mutations, repairs=self.repairs, notes=self.notes,
            retrieval_provider=lambda: self.retrieval, faults=faults,
        )

    async def turn(self, question="原始问题"):
        record = await self.conversations.create_conversation("t")
        prepared = await self.conversations.prepare_turn(record.id, question, request_id=uuid.uuid4().hex)
        self.conversations.finish_run(prepared, checkpoint_id_of(prepared.config), "completed")
        return record, prepared

    def owned_write(self, conversation_id, name="A.md", content="v1\n", op="op-1"):
        return self.mutations.apply(
            MutationCommand(kind=CREATE, file_name=name, title="A", content=content),
            Origin(kind="conversation", conversation_id=conversation_id), op,
            retrieval=self.retrieval,
        )

    def job(self, operation_id):
        with self.factory() as session:
            return session.scalar(select(RecoveryJob).where(RecoveryJob.operation_id == operation_id))


async def test_start_restores_files_forks_and_publishes(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    assert env.notes.exists("A.md") and env.retrieval.is_indexed("A.md")
    revision = env.conversations.get(record.id).revision

    preview_id, plan = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改过的问题", expected_revision=revision
    )
    assert plan.can_apply and plan.requires_confirmation
    assert [c.path for c in plan.file_changes] == ["A.md"]

    job = await env.coordinator.start(
        preview_id, "改过的问题", [c.path for c in plan.file_changes], "op-job-1"
    )
    assert job["status"] == "succeeded"
    assert not env.notes.exists("A.md")          # created after the boundary -> deleted
    assert env.retrieval.indexed == set()        # index was repaired for the affected path
    assert job["prepared_turn_id"]
    assert env.gate.maintenance() is None

    # The edited user message is the active head; the original is not re-inserted.
    messages = await env.conversations.list_messages(record.id)
    assert messages[-1].content == "改过的问题"

    again = await env.coordinator.start(
        preview_id, "改过的问题", [c.path for c in plan.file_changes], "op-job-1"
    )
    assert again["job_id"] == job["job_id"]


async def test_git_fault_keeps_maintenance_and_retry_completes(tmp_path):
    faults = FailInjector()
    env = _Env(tmp_path, faults=faults)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    revision = env.conversations.get(record.id).revision
    preview_id, plan = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改后", expected_revision=revision
    )
    confirmed = [c.path for c in plan.file_changes]

    faults.inject("git_committed")
    with pytest.raises(Exception):
        await env.coordinator.start(preview_id, "改后", confirmed, "op-job-2")

    job = env.job("op-job-2")
    assert job is not None and job.status == "failed"
    # Maintenance blocks every gated mode even though the files were rolled back.
    assert env.gate.maintenance() is not None
    with pytest.raises(WorkspaceBusy):
        with env.gate.operation("read"):
            pass

    retried = await env.coordinator.retry(str(job.id), "op-job-2")
    assert retried["status"] == "succeeded"
    assert env.gate.maintenance() is None


async def test_later_change_to_owned_file_blocks_the_plan(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    # Another origin edits the same file after the conversation's write.
    env.mutations.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="someone else", append=True),
        Origin.library(), "lib-1", retrieval=env.retrieval,
    )
    revision = env.conversations.get(record.id).revision
    preview_id, plan = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改", expected_revision=revision
    )
    assert not plan.can_apply
    with pytest.raises(PlanConflict):
        await env.coordinator.start(preview_id, "改", [], "op-job-3")


async def test_confirmation_is_required_for_file_changes(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    revision = env.conversations.get(record.id).revision
    preview_id, plan = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改", expected_revision=revision
    )
    assert plan.requires_confirmation
    with pytest.raises(ConfirmationRequired):
        await env.coordinator.start(preview_id, "改", [], "op-job-4")
