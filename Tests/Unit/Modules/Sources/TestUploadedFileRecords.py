"""上传记录与聊天来源分离后的可观察行为。"""
import hashlib
import zipfile
from io import BytesIO

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileError, SourceFileService
from NoteAgent.Modules.Sources.Service.SourceFileWorker import SourceFileWorker
from NoteAgent.Common.Database.OrmBase import Base
from NoteAgent.Modules.Sources.Storage.LocalSourceFileStore import LocalSourceFileStore


@pytest.fixture
def service(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    engine.dispose()


def test_known_format_rejects_declared_mime_conflict(service):
    with pytest.raises(SourceFileError):
        service.upload("a.pdf", b"%PDF-1.4\n", content_type="image/png")
    assert service.list() == []


def test_known_format_rejects_missing_mime(service):
    with pytest.raises(SourceFileError):
        service.upload("a.txt", b"hello", content_type="")
    assert service.list() == []


def test_text_extension_rejects_binary_content(service):
    with pytest.raises(SourceFileError):
        service.upload("a.txt", b"hello\x00world", content_type="text/plain")
    assert service.list() == []


def test_known_docx_content_cannot_hide_behind_unknown_extension(service):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(SourceFileError):
        service.upload("renamed.xyz", buffer.getvalue(), content_type="application/x-custom")
    assert service.list() == []


def test_unknown_format_has_independent_record_but_cannot_be_chat_source(service):
    data = b"arbitrary binary\x00\x01"
    source = service.upload("archive.xyz", data, content_type="application/x-custom")
    assert source.status == "stored"
    assert source.original_filename == "archive.xyz"
    assert source.storage_path == str(source.id)
    assert source.media_type == "application/octet-stream"
    assert source.size_bytes == len(data)
    assert source.sha256 == hashlib.sha256(data).hexdigest()
    assert service.store.read(str(source.id)) == data
    assert SourceFileWorker(service).run_once() is False
    with pytest.raises(SourceFileError):
        service.ready_attachments([str(source.id)])


def test_same_bytes_keep_distinct_names_ids_and_delete_lifecycles(service):
    first = service.upload("first.txt", b"same", content_type="text/plain")
    second = service.upload("second.txt", b"same", content_type="text/plain")
    assert first.id != second.id
    assert first.sha256 == second.sha256
    service.delete(str(first.id))
    assert service.get(str(second.id)).status == "queued"
    assert service.store.read(str(second.id)) == b"same"


def test_rename_preserves_original_filename(service):
    source = service.upload("original.txt", b"hello", content_type="text/plain")
    changed = service.rename(str(source.id), "display.txt", "folder")
    assert changed.display_name == "display.txt"
    assert changed.original_filename == "original.txt"
