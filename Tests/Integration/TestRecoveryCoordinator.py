"""Recovery coordinator: staged restore, idempotency, maintenance and conflicts."""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CheckpointRuntime, checkpoint_id_of
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationService
from NoteAgent.TechnicalSupport.DatabaseAccess import Base, create_engine_from_url, create_session_factory, load_all_models
from NoteAgent.BusinessModules.NoteStorage.NoteChanges import CREATE, WRITE, MutationCommand, NoteMutationService, Origin
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteStorage.NoteVersions import NoteVersionStore
from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import WorkspaceBusy, WorkspaceGate
from NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels import RecoveryJob
from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import ConfirmationRequired, PlanConflict, RecoveryCoordinator
from NoteAgent.BusinessModules.NoteRetrieval.IndexRepair.IndexRepairService import IndexRepairService
from Support.Fakes import FailInjector


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

async def test_stale_preview_preserves_later_library_write(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    env.owned_write(c.id)
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    env.mutations.apply(MutationCommand(kind=WRITE, file_name='A.md', content='later', append=False), Origin.library(), 'library', retrieval=env.retrieval)
    with pytest.raises((PlanConflict, Exception)) as error:
        await env.coordinator.start(pid, 'edited', [x.path for x in p.file_changes], 'restore')
    assert 'later' in env.notes.read('A.md')
    assert env.gate.maintenance() is None

async def test_failed_index_blocks_publication(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    env.owned_write(c.id)
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    original = env.conversations.recovery_context(c.id)
    def fail(name): raise RuntimeError('vector unavailable')
    env.retrieval.delete_note = fail
    with pytest.raises(Exception):
        await env.coordinator.start(pid, 'edited', [x.path for x in p.file_changes], 'restore')
    assert env.conversations.recovery_context(c.id) == original
    assert env.gate.maintenance() is not None

@pytest.mark.parametrize('stage', ['candidate_saved', 'before_publish', 'after_publish'])
async def test_candidate_and_publication_retry_is_idempotent(tmp_path, stage):
    faults = FailInjector()
    env = _Env(tmp_path, faults=faults)
    c, t = await env.turn()
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    faults.inject(stage)
    try:
        await env.coordinator.start(pid, 'edited', [], 'restore')
    except Exception:
        pass
    job = env.job('restore')
    retried = await env.coordinator.retry(str(job.id), 'restore')
    assert retried['status'] == 'succeeded'
    assert env.gate.maintenance() is None
    assert len(await env.conversations.list_messages(c.id)) == 1

async def test_recovered_turn_can_finish_and_resume(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    j = await env.coordinator.start(pid, 'edited', [], 'restore')
    run = env.conversations.claim_prepared(j['prepared_turn_id'])
    messages = await env.conversations.list_messages(c.id)
    assert messages[-1].id == run.user_message_id
    env.conversations.interrupt_run(run)
    resumed = env.conversations.resume_turn(run.run_id, conversation_id=c.id)
    env.conversations.finish_run(resumed, checkpoint_id_of(resumed.config), 'completed')
    assert env.conversations.get_active_run(c.id) is None

async def test_external_edit_before_preview_is_conflict(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    env.owned_write(c.id)
    env.notes.path_of('A.md').write_bytes(b'external keep')
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    assert not p.can_apply
    with pytest.raises(PlanConflict):
        await env.coordinator.start(pid, 'edited', ['A.md'], 'restore')
    assert env.notes.path_of('A.md').read_bytes() == b'external keep'

async def test_owned_note_in_new_folder_rolls_back_file_and_folder(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    env.owned_write(c.id, name='New/A.md')
    pid, p = await env.coordinator.preview(c.id, t.user_message_id, 'edited')
    assert p.can_apply
    await env.coordinator.start(pid, 'edited', [x.path for x in p.file_changes] + [x.path for x in p.folder_changes], 'restore')
    assert not env.notes.exists('New/A.md')
    assert env.notes.list_folders() == []

async def test_recovery_preserves_boundary_draft_and_compacted_records(tmp_path):
    env = _Env(tmp_path)
    c = await env.conversations.create_conversation('t')
    view = await env.conversations.get_state(c.id)
    state = dict(view.values)
    state['working_records'] = []
    state['running_summary'] = 'summary'
    state['pending_draft'] = {'action': 'create', 'file_name': 'Pending.md', 'content': 'draft'}
    await env.conversations.write_state(c.id, state, branch_id=state['branch_id'], publish=True)
    turn = await env.conversations.prepare_turn(c.id, 'original', 'original')
    env.conversations.finish_run(turn, checkpoint_id_of(turn.config), 'completed')
    pid, p = await env.coordinator.preview(c.id, turn.user_message_id, 'edited')
    await env.coordinator.start(pid, 'edited', [], 'restore')
    restored = (await env.conversations.get_state(c.id)).values
    assert restored['running_summary'] == 'summary'
    assert restored['pending_draft']['content'] == 'draft'
    assert [m['content'] for m in restored['working_records']] == ['edited']


async def test_accepted_prepared_recovery_survives_expired_lease(tmp_path):
    from datetime import datetime, timedelta, timezone
    from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationRun
    env = _Env(tmp_path)
    c, turn = await env.turn()
    pid, _ = await env.coordinator.preview(c.id, turn.user_message_id, 'edited')
    job = await env.coordinator.start(pid, 'edited', [], 'restore')
    with env.factory() as session:
        run = session.get(ConversationRun, uuid.UUID(job['prepared_turn_id']))
        run.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()
    claimed = env.conversations.claim_prepared(job['prepared_turn_id'], conversation_id=c.id)
    assert claimed.user_message_id == (await env.conversations.list_messages(c.id))[-1].id


async def test_new_untracked_attachment_after_preview_is_preserved(tmp_path):
    env = _Env(tmp_path)
    c, turn = await env.turn()
    env.owned_write(c.id, name='New/A.md')
    pid, p = await env.coordinator.preview(c.id, turn.user_message_id, 'edited')
    attachment = env.notes.root / 'New/attachment.txt'
    attachment.write_bytes(b'keep')
    with pytest.raises(PlanConflict):
        await env.coordinator.start(pid, 'edited', [x.path for x in p.file_changes] + [x.path for x in p.folder_changes], 'restore')
    assert attachment.read_bytes() == b'keep'
    assert env.notes.exists('New/A.md')


async def test_folder_rename_restores_notes_and_attachments(tmp_path):
    from NoteAgent.BusinessModules.NoteStorage.NoteChanges import FOLDER_RENAME
    env = _Env(tmp_path)
    env.notes.create('Old/A.md', 'A')
    attachment = env.notes.root / 'Old/attachment.txt'
    attachment.write_bytes(b'attachment')
    c, turn = await env.turn()
    env.mutations.apply(MutationCommand(kind=FOLDER_RENAME, name='Old', dest='New'),
                        Origin(kind='conversation', conversation_id=c.id), 'rename', retrieval=env.retrieval)
    pid, p = await env.coordinator.preview(c.id, turn.user_message_id, 'edited')
    assert p.can_apply, p.conflicts
    await env.coordinator.start(pid, 'edited', [x.path for x in p.file_changes] + [x.path for x in p.folder_changes], 'restore')
    assert env.notes.exists('Old/A.md')
    assert attachment.read_bytes() == b'attachment'
    assert not (env.notes.root / 'New').exists()
