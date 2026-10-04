"""Recovery HTTP layer: preview, confirmation, conflicts, job status and retry."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from noteagent.conversations.contracts import TurnAlreadyClaimed
from noteagent.notes.mutations import WRITE, MutationCommand, Origin
from noteagent.recovery.models import RecoveryJob
from noteagent.recovery.router import recovery_error_handler, router as recovery_router
from noteagent.recovery.service import RecoveryError
from support.fakes import FailInjector

from test_recovery_coordinator import _Env


def _client(coordinator) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RecoveryError, recovery_error_handler)
    app.include_router(recovery_router)
    app.state.container = SimpleNamespace(recovery=coordinator)
    # A failed recovery surfaces as a 500; the test asserts the status, not the raise.
    return TestClient(app, raise_server_exceptions=False)


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
