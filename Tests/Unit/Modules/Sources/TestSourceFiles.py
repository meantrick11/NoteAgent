from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from NoteAgent.Modules.Sources.Domain.Po.SourceFileModels import SourceFile, SourceFragment
from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService, SourceFileError
from NoteAgent.Modules.Sources.Service.SourceFileWorker import SourceFileWorker
from NoteAgent.Common.Database.OrmBase import Base
from NoteAgent.Modules.Sources.Storage.LocalSourceFileStore import LocalSourceFileStore


@pytest.fixture
def service(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    engine.dispose()


def test_duplicate_content_keeps_independent_identity(service):
    first = service.upload("a.txt", b"hello", content_type="text/plain")
    second = service.upload("b.txt", b"hello", content_type="text/plain")
    assert first.id != second.id
    assert service.store.read(str(first.id)) == b"hello"


def test_upload_rejects_fake_format_and_unsafe_name(service):
    with pytest.raises(SourceFileError):
        service.upload("../bad.txt", b"hello", content_type="text/plain")
    with pytest.raises(SourceFileError):
        service.upload("fake.pdf", b"hello", content_type="application/pdf")


def test_rename_does_not_change_identity(service):
    source = service.upload("a.txt", b"hello", content_type="text/plain")
    renamed = service.rename(str(source.id), "b.txt", "work")
    assert renamed.id == source.id
    assert service.store.read(str(source.id)) == b"hello"


def test_delete_preserves_tombstone(service):
    source = service.upload("a.txt", b"hello", content_type="text/plain")
    service.delete(str(source.id))
    assert service.get(str(source.id)).status == "deleted"
    with pytest.raises(SourceFileError):
        service.read_fragments(str(source.id))
    replacement = service.upload("again.txt", b"hello", content_type="text/plain")
    assert replacement.id != source.id
    assert service.get(str(source.id)).status == "deleted"


def test_worker_publishes_complete_text(service):
    source = service.upload("a.txt", b"hello", content_type="text/plain")
    worker = SourceFileWorker(service)
    assert worker.run_once()
    assert service.get(str(source.id)).status == "ready"
    assert service.read_fragments(str(source.id))[0].text == "hello"


def test_worker_fails_empty_content_without_fragments(service):
    source = service.upload("a.txt", b"  ", content_type="text/plain")
    worker = SourceFileWorker(service)
    assert worker.run_once()
    assert service.get(str(source.id)).status == "failed"
    with pytest.raises(SourceFileError):
        service.read_fragments(str(source.id))


def test_worker_reclaims_interrupted_parse_on_restart(service):
    source = service.upload("a.txt", b"hello", content_type="text/plain")
    with service.sessions.begin() as session:
        session.get(SourceFile, source.id).status = "parsing"
    worker = SourceFileWorker(service)
    worker.reset_incomplete()
    assert service.get(str(source.id)).status == "queued"
    assert worker.run_once()
    assert service.get(str(source.id)).status == "ready"
