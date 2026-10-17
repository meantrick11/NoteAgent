from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService
from NoteAgent.Modules.Sources.Service.SourceFileWorker import SourceFileWorker
from NoteAgent.Modules.Sources.Router.SourceFileRoutes import router
from NoteAgent.Common.Database.OrmBase import Base
from NoteAgent.Modules.Sources.Storage.LocalSourceFileStore import LocalSourceFileStore


def test_upload_parse_preview_and_delete(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service = SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    app.state.container = SimpleNamespace(
        source_files=service,
        model_runtime=SimpleNamespace(status=lambda: SimpleNamespace(active_chat=None, revision=0)),
    )
    client = TestClient(app)
    response = client.post("/source-files", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 201
    source_id = response.json()["id"]
    assert response.json()["status"] == "queued"
    SourceFileWorker(service).run_once()
    assert client.get(f"/source-files/{source_id}").json()["status"] == "ready"
    assert client.get(f"/source-files/{source_id}/preview").json()["fragments"][0]["text"] == "hello"
    assert client.get(f"/source-files/{source_id}/download").content == b"hello"
    assert client.delete(f"/source-files/{source_id}").status_code == 204
    assert client.get(f"/source-files/{source_id}").json()["status"] == "deleted"


def test_upload_rejects_spoofed_pdf(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service = SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    app.state.container = SimpleNamespace(source_files=service,
        model_runtime=SimpleNamespace(status=lambda: SimpleNamespace(active_chat=None, revision=0)))
    response = TestClient(app).post("/source-files", files={"file": ("fake.pdf", b"not-a-pdf", "application/pdf")})
    assert response.status_code == 400
    assert service.list() == []


def test_upload_rejects_mime_conflict_and_exposes_record_fields(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service = SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    app.state.container = SimpleNamespace(source_files=service,
        model_runtime=SimpleNamespace(status=lambda: SimpleNamespace(active_chat=None, revision=0)))
    client = TestClient(app)
    rejected = client.post("/source-files", files={"file": ("lesson.txt", b"hello", "image/png")})
    assert rejected.status_code == 400
    assert service.list() == []
    stored = client.post("/source-files", files={"file": ("payload.xyz", b"binary\x00", "application/x-custom")})
    assert stored.status_code == 201
    body = stored.json()
    assert body["status"] == "stored"
    assert body["original_filename"] == "payload.xyz"
    assert body["storage_path"] == body["id"]
    assert body["sha256"] == "6c0f1f54ea7ef81bd827ae3e93cbc4f3190cd7c01d7df5897d8caea2f0a7a3ed"
    assert client.get(f"/source-files/{body['id']}/download").content == b"binary\x00"


def test_cross_origin_upload_is_refused(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service = SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    app.state.container = SimpleNamespace(source_files=service,
        model_runtime=SimpleNamespace(status=lambda: SimpleNamespace(active_chat=None, revision=0)))
    response = TestClient(app).post("/source-files", files={"file": ("a.txt", b"hello", "text/plain")},
                                    headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
    assert service.list() == []
