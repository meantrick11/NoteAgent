"""Recovery HTTP layer: preview, confirmation, conflicts, job status and retry."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from NoteAgent.BusinessModules.ConversationState.ConversationContracts import TurnAlreadyClaimed
from NoteAgent.BusinessModules.NoteStorage.NoteChanges import WRITE, MutationCommand, Origin
from NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels import RecoveryJob
from NoteAgent.HttpApi.HttpErrors import recovery_error_handler
from NoteAgent.HttpApi.ConversationRecoveryApi.ConversationRecoveryRoutes import router as recovery_router
from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import RecoveryError
from Support.Fakes import FailInjector

from TestRecoveryCoordinator import _Env


def _client(coordinator) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RecoveryError, recovery_error_handler)
    app.include_router(recovery_router)
    app.state.container = SimpleNamespace(recovery=coordinator)
    # A failed recovery surfaces as a 500; the test asserts the status, not the raise.
    return TestClient(app, raise_server_exceptions=False)


def test_formal_library_folder_mutations_use_real_names_and_repair_paths(tmp_path):
    from Support.DurableApp import build_durable_app
    app = build_durable_app(tmp_path)
    client = app.client
    created = client.post('/notes/folders', json={'name': 'Old'})
    assert created.status_code == 200 and created.json()['name'] == 'Old'
    note = client.post('/notes', json={'file_name': 'Old/A.md'})
    assert note.status_code == 200
    moved = client.post('/notes/folders/rename', json={'from_path': 'Old', 'to_path': 'New'})
    assert moved.status_code == 200, moved.text
    assert moved.json()['files'] == ['New/A.md']
    assert not app.container.retrieval.is_indexed('Old/A.md')
    assert app.container.mutations._repairs.is_synced('New/A.md', app.container.retrieval)
    app.container.mutations._repairs._mark('New/A.md', 'failed')
    assert client.post('/notes/New/A.md/index').json()['indexed']
    assert app.container.mutations._repairs.is_synced('New/A.md', app.container.retrieval)
    removed = client.delete('/notes/folders/New')
    assert removed.status_code == 200, removed.text
    assert not app.notes.list_notes()
    assert not app.container.retrieval.is_indexed('New/A.md')


async def test_preview_then_confirmation_required_then_start(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    revision = env.conversations.get(record.id).revision
    client = _client(env.coordinator)

    preview = client.post(
        f"/conversations/{record.id}/recoveries/preview",
        json={"message_id": prepared.user_message_id, "edited_content": "改过",
              "expected_revision": revision},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["can_apply"] and body["requires_confirmation"]
    assert [c["path"] for c in body["file_changes"]] == ["A.md"]
    # The preview changed nothing on disk.
    assert env.notes.exists("A.md")

    # No confirmation of the file change -> refused.
    refused = client.post(
        f"/conversations/{record.id}/recoveries",
        json={"preview_id": body["preview_id"], "edited_content": "改过",
              "confirmed_file_changes": [], "operation_id": "api-op-1"},
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "confirmation_required"

    started = client.post(
        f"/conversations/{record.id}/recoveries",
        json={"preview_id": body["preview_id"], "edited_content": "改过",
              "confirmed_file_changes": ["A.md"], "operation_id": "api-op-2"},
    )
    assert started.status_code == 200
    job = started.json()
    assert job["status"] == "succeeded" and job["prepared_turn_id"]
    assert not env.notes.exists("A.md")

    # A recovery-forked prepared turn is claimed exactly once.
    first = env.conversations.claim_prepared(job["prepared_turn_id"])
    assert first.user_message_id
    with pytest.raises(TurnAlreadyClaimed):
        env.conversations.claim_prepared(job["prepared_turn_id"])


async def test_conflict_is_reported_without_body_change(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    env.mutations.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="other", append=True),
        Origin.library(), "lib-x", retrieval=env.retrieval,
    )
    before = env.notes.path_of("A.md").read_bytes()
    client = _client(env.coordinator)
    revision = env.conversations.get(record.id).revision

    preview = client.post(
        f"/conversations/{record.id}/recoveries/preview",
        json={"message_id": prepared.user_message_id, "edited_content": "改",
              "expected_revision": revision},
    )
    body = preview.json()
    assert body["can_apply"] is False and body["conflicts"]

    posted = client.post(
        f"/conversations/{record.id}/recoveries",
        json={"preview_id": body["preview_id"], "edited_content": "改",
              "confirmed_file_changes": [], "operation_id": "api-op-3"},
    )
    assert posted.status_code == 409
    assert posted.json()["code"] == "conflict"
    assert env.notes.path_of("A.md").read_bytes() == before


async def test_job_available_during_maintenance_and_retry_completes(tmp_path):
    faults = FailInjector()
    env = _Env(tmp_path, faults=faults)
    record, prepared = await env.turn()
    env.owned_write(record.id)
    revision = env.conversations.get(record.id).revision
    client = _client(env.coordinator)

    preview = client.post(
        f"/conversations/{record.id}/recoveries/preview",
        json={"message_id": prepared.user_message_id, "edited_content": "改",
              "expected_revision": revision},
    ).json()

    faults.inject("git_committed")
    started = client.post(
        f"/conversations/{record.id}/recoveries",
        json={"preview_id": preview["preview_id"], "edited_content": "改",
              "confirmed_file_changes": ["A.md"], "operation_id": "api-op-4"},
    )
    assert started.status_code == 500

    with env.factory() as session:
        job = session.scalar(select(RecoveryJob).where(RecoveryJob.operation_id == "api-op-4"))
        job_id = str(job.id)
    assert env.gate.maintenance() is not None

    # Status is readable while maintenance blocks every gated mode.
    status = client.get(f"/recoveries/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "failed"

    retried = client.post(f"/recoveries/{job_id}/retry", json={"operation_id": "api-op-4"})
    assert retried.status_code == 200
    assert retried.json()["status"] == "succeeded"
    assert env.gate.maintenance() is None

async def test_wrong_conversation_recovery_has_no_side_effect(tmp_path):
    env = _Env(tmp_path)
    c, t = await env.turn()
    other, _ = await env.turn('other')
    env.owned_write(c.id)
    pid, plan = await env.coordinator.preview(c.id, t.user_message_id, 'edit')
    before = env.notes.read('A.md')
    response = _client(env.coordinator).post(f'/conversations/{other.id}/recoveries', json={'preview_id': pid, 'edited_content': 'edit', 'confirmed_file_changes': ['A.md'], 'operation_id': 'wrong'})
    assert response.status_code == 404
    assert env.notes.read('A.md') == before
    assert env.gate.maintenance() is None

async def test_formal_message_can_edit_and_prepared_turn_finishes(tmp_path):
    import json
    from Support.Webapp import build_checkpoint_app
    from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import RecoveryCoordinator
    from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import WorkspaceGate
    from NoteAgent.BusinessModules.NoteStorage.NoteVersions import NoteVersionStore
    from NoteAgent.BusinessModules.NoteStorage.NoteChanges import NoteMutationService
    from NoteAgent.BusinessModules.NoteRetrieval.IndexRepair.IndexRepairService import IndexRepairService
    from NoteAgent.TechnicalSupport.DatabaseAccess import create_session_factory
    app = build_checkpoint_app(tmp_path / 'app', reply_batches=[['first', 'recomputed']])
    factory = create_session_factory(app.container.engine)
    gate = WorkspaceGate(factory); gate.ensure_row()
    app.container.workspace = gate
    app.container.model_runtime._workspace = gate
    repair = IndexRepairService(factory, app.notes)
    mutations = NoteMutationService(app.notes, NoteVersionStore(tmp_path / 'history', app.notes.root), gate, factory, repairs=repair)
    app.container.mutations = mutations
    app.container.recovery = RecoveryCoordinator(session_factory=factory, gate=gate, conversations=app.service, mutations=mutations, repairs=repair, notes=app.notes, retrieval_provider=lambda: app.agent_retrieval)
    response = app.client.post('/chat', json={'question': 'original'})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: {')]
    cid = next(e['id'] for e in events if 'title' in e)
    messages = app.client.get(f'/conversations/{cid}/messages').json()
    assert messages[0]['editable'] is True
    preview = app.client.post(f'/conversations/{cid}/recoveries/preview', json={'message_id': messages[0]['id'], 'edited_content': 'edited'}).json()
    job_response = app.client.post(f'/conversations/{cid}/recoveries', json={'preview_id': preview['preview_id'], 'edited_content': 'edited', 'confirmed_file_changes': [], 'operation_id': 'formal'})
    assert job_response.status_code == 200
    job = job_response.json()
    result = app.client.post('/chat', json={'conversation_id': cid, 'prepared_turn_id': job['prepared_turn_id']})
    assert result.status_code == 200
    assert 'recomputed' in result.text
    detail = app.client.get(f'/conversations/{cid}').json()
    assert detail['active_run'] is None
    updated = app.client.get(f'/conversations/{cid}/messages').json()
    assert [m['content'] for m in updated] == ['edited', 'recomputed']
    assert updated[0]['editable'] is True
