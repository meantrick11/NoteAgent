"""Source file validation, identity and lifecycle; no note indexing occurs here."""
from __future__ import annotations
import hashlib
import uuid
import zipfile
from io import BytesIO
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from NoteAgent.BusinessModules.SourceFiles.SourceFileModels import SourceFile, SourceFolder, SourceFragment
from NoteAgent.BusinessModules.SourceFiles.SourceFileRepository import SourceFileRepository
from NoteAgent.TechnicalSupport.SourceFileStorage.LocalSourceFileStore import LocalSourceFileStore

MAX_BYTES = 20 * 1024 * 1024
MEDIA_TYPES = {
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain", ".md": "text/markdown", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}
ALLOWED_MIME = {suffix: {media} for suffix, media in MEDIA_TYPES.items()}
ALLOWED_MIME[".md"].add("text/plain")
ALLOWED_MIME[".md"].add("text/x-markdown")


class SourceFileError(ValueError):
    pass


def _name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 255 or any(c in name for c in ("/", "\\", "\0")) or name in (".", ".."):
        raise SourceFileError("文件名无效")
    return name


def _signature_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if {"[Content_Types].xml", "word/document.xml"} <= set(archive.namelist()):
                    return MEDIA_TYPES[".docx"]
        except zipfile.BadZipFile:
            pass
    return None


def _media(name: str, data: bytes, content_type: str | None) -> str:
    suffix = PurePath(name).suffix.lower()
    media = MEDIA_TYPES.get(suffix)
    if media is None:
        if _signature_type(data) is not None:
            raise SourceFileError("文件后缀与实际内容不符")
        return "application/octet-stream"
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared not in ALLOWED_MIME[suffix]:
        raise SourceFileError("文件 MIME 与后缀不符或缺失")
    signature = _signature_type(data)
    if signature is not None and signature != media:
        raise SourceFileError("文件头与后缀不符")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise SourceFileError("文件内容与 PDF 格式不符")
    if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SourceFileError("文件内容与 PNG 格式不符")
    if suffix in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        raise SourceFileError("文件内容与 JPEG 格式不符")
    if suffix == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise SourceFileError("文件内容与 DOCX 格式不符")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
                if not {"[Content_Types].xml", "word/document.xml"} <= names:
                    raise SourceFileError("文件内容与 DOCX 格式不符")
                if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                    raise SourceFileError("DOCX 解压内容超过 40 MB")
        except zipfile.BadZipFile as exc:
            raise SourceFileError("DOCX 文件损坏") from exc
    if suffix in (".txt", ".md"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceFileError("文本文件需要 UTF-8 编码") from exc
        if any(byte < 32 and byte not in (9, 10, 13) for byte in data):
            raise SourceFileError("文本文件包含二进制控制字符")
    return media


class SourceFileService:
    def __init__(self, sessions: sessionmaker[Session], store: LocalSourceFileStore):
        self.sessions = sessions
        self.store = store
        self.repository = SourceFileRepository(sessions)

    def upload(self, filename: str, data: bytes, *, content_type: str | None,
               profile_id: str | None = None, profile_revision: int | None = None) -> SourceFile:
        name = _name(filename)
        if not data or len(data) > MAX_BYTES:
            raise SourceFileError("文件为空或超过 20 MB")
        media = _media(name, data, content_type)
        digest = hashlib.sha256(data).hexdigest()
        source_id = uuid.uuid4()
        try:
            with self.sessions.begin() as session:
                source = SourceFile(id=source_id, original_filename=name, storage_path=str(source_id),
                                    display_name=name, media_type=media, size_bytes=len(data), sha256=digest,
                                    status="queued" if media != "application/octet-stream" else "stored",
                                    parse_profile_id=profile_id, parse_profile_revision=profile_revision)
                self.store.write(str(source_id), data)
                session.add(source)
                session.flush()
                session.expunge(source)
                return source
        except BaseException:
            self.store.delete(str(source_id))
            raise

    def get(self, source_id: str) -> SourceFile:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceFileError("来源文件不存在")
        return source

    def list(self) -> list[SourceFile]:
        return self.repository.list()

    def rename(self, source_id: str, name: str | None, folder: str | None) -> SourceFile:
        with self.sessions.begin() as session:
            source = session.get(SourceFile, uuid.UUID(source_id))
            if source is None or source.status == "deleted":
                raise SourceFileError("来源文件不可用")
            if name is not None:
                source.display_name = _name(name)
            if folder is not None:
                if folder:
                    _name(folder)
                    if session.get(SourceFolder, folder) is None:
                        session.add(SourceFolder(name=folder))
                source.folder = folder
            session.flush()
            session.expunge(source)
            return source

    def delete(self, source_id: str) -> None:
        with self.sessions.begin() as session:
            source = session.get(SourceFile, uuid.UUID(source_id))
            if source is None:
                raise SourceFileError("来源文件不存在")
            source.status = "deleted"
            session.flush()
        # Tombstone stays; in-flight readers may already hold bytes in memory.
        self.store.delete(source_id)

    def read_fragments(self, source_id: str) -> list[SourceFragment]:
        with self.sessions() as session:
            source = session.get(SourceFile, uuid.UUID(source_id))
            if source is None or source.status != "ready":
                raise SourceFileError("来源文件尚未就绪或已不可用")
            parts = list(session.scalars(select(SourceFragment).where(SourceFragment.source_file_id == source.id).order_by(SourceFragment.ordinal)))
            for part in parts:
                session.expunge(part)
            return parts

    def retry(self, source_id: str, *, profile_id: str | None = None, profile_revision: int | None = None) -> SourceFile:
        with self.sessions.begin() as session:
            source = session.get(SourceFile, uuid.UUID(source_id))
            if source is None or source.status != "failed":
                raise SourceFileError("仅失败文件可重试")
            source.status = "queued"
            source.error = None
            source.parse_profile_id = profile_id
            source.parse_profile_revision = profile_revision
            session.flush()
            session.expunge(source)
            return source

    def ready_attachments(self, ids: list[str]) -> list[dict]:
        if len(ids) > 5 or len(set(ids)) != len(ids):
            raise SourceFileError("每条消息最多 5 个不同附件")
        result = []
        for source_id in ids:
            try:
                source = self.get(source_id)
            except (ValueError, SourceFileError) as exc:
                raise SourceFileError("附件 ID 无效") from exc
            if source.status != "ready":
                raise SourceFileError(f"附件 {source.display_name} 尚未就绪或已不可用")
            result.append({"id": str(source.id), "name": source.display_name,
                           "parse_profile_revision": source.parse_profile_revision})
        return result
