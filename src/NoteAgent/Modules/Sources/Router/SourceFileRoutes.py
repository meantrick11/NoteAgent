"""Upload, inspect, organize and retry source files without touching notes or Chroma."""
from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import delete, select

from NoteAgent.Modules.Sources.Domain.Po.SourceFileModels import SourceFile, SourceFolder
from NoteAgent.Modules.Sources.Service.SourceFileService import MAX_BYTES, SourceFileError, _name
from NoteAgent.Modules.Sources.Domain.Dto.SourceFileSchemas import FolderIn, FolderRenameIn, SourceFileOut, SourceFilePatch
from NoteAgent.Common.Http.RequestDependencies import require_same_origin

router = APIRouter(prefix="/source-files", tags=["source-files"], dependencies=[Depends(require_same_origin)])


def _service(request: Request):
    service = getattr(request.app.state.container, "source_files", None)
    if service is None:
        raise HTTPException(503, "source file service unavailable")
    return service


def _out(source: SourceFile) -> SourceFileOut:
    return SourceFileOut(
        id=str(source.id), original_filename=source.original_filename, storage_path=source.storage_path,
        display_name=source.display_name, folder=source.folder,
        media_type=source.media_type, size_bytes=source.size_bytes, sha256=source.sha256, status=source.status,
        error=source.error, created_at=source.created_at, updated_at=source.updated_at,
    )


def _error(exc: Exception):
    raise HTTPException(400, str(exc)) from exc


@router.post("", response_model=SourceFileOut, status_code=201)
async def upload(request: Request, file: UploadFile = File(...)):
    service = _service(request)
    data = await file.read(MAX_BYTES + 1)
    status = request.app.state.container.model_runtime.status()
    model = status.active_model
    try:
        source = service.upload(file.filename or "", data, content_type=file.content_type,
                                profile_id=model.id if model else None,
                                profile_revision=model.revision if model else None)
    except SourceFileError as exc:
        _error(exc)
    return _out(source)


@router.get("", response_model=list[SourceFileOut])
def list_sources(request: Request):
    return [_out(item) for item in _service(request).list()]


@router.get("/folders")
def list_folders(request: Request):
    service = _service(request)
    with service.sessions() as session:
        return {"folders": list(session.scalars(select(SourceFolder.name).order_by(SourceFolder.name)))}


@router.post("/folders", status_code=201)
def create_folder(request: Request, body: FolderIn):
    service = _service(request)
    try:
        name = _name(body.name)
        with service.sessions.begin() as session:
            if session.get(SourceFolder, name):
                raise SourceFileError("文件夹已存在")
            session.add(SourceFolder(name=name))
        return {"name": name}
    except SourceFileError as exc:
        _error(exc)


@router.patch("/folders/{name}")
def rename_folder(request: Request, name: str, body: FolderRenameIn):
    service = _service(request)
    try:
        target = _name(body.name)
        with service.sessions.begin() as session:
            folder = session.get(SourceFolder, name)
            if folder is None or session.get(SourceFolder, target):
                raise SourceFileError("文件夹不存在或目标已存在")
            session.add(SourceFolder(name=target))
            for source in session.scalars(select(SourceFile).where(SourceFile.folder == name)):
                source.folder = target
            session.delete(folder)
        return {"name": target}
    except SourceFileError as exc:
        _error(exc)


@router.delete("/folders/{name}", status_code=204)
def delete_folder(request: Request, name: str):
    service = _service(request)
    with service.sessions.begin() as session:
        folder = session.get(SourceFolder, name)
        if folder is None:
            raise HTTPException(404, "文件夹不存在")
        for source in session.scalars(select(SourceFile).where(SourceFile.folder == name)):
            source.folder = ""
        session.delete(folder)
    return Response(status_code=204)


@router.get("/{source_id}", response_model=SourceFileOut)
def get_source(request: Request, source_id: uuid.UUID):
    try:
        return _out(_service(request).get(str(source_id)))
    except SourceFileError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{source_id}/preview")
def preview(request: Request, source_id: uuid.UUID):
    service = _service(request)
    try:
        source = service.get(str(source_id))
        if source.status != "ready":
            raise SourceFileError("来源文件尚未就绪或已不可用")
        if source.media_type in ("application/pdf", "image/png", "image/jpeg"):
            return Response(service.store.read(str(source_id)), media_type=source.media_type,
                            headers={"Content-Disposition": "inline"})
        return {"fragments": [{"ordinal": p.ordinal, "locator": p.locator, "text": p.text}
                              for p in service.read_fragments(str(source_id))]}
    except SourceFileError as exc:
        _error(exc)


@router.get("/{source_id}/download")
def download(request: Request, source_id: uuid.UUID):
    service = _service(request)
    try:
        source = service.get(str(source_id))
        if source.status == "deleted":
            raise SourceFileError("来源文件已删除")
        return Response(service.store.read(str(source_id)), media_type=source.media_type,
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(source.display_name)}"})
    except (SourceFileError, FileNotFoundError) as exc:
        _error(exc)


@router.patch("/{source_id}", response_model=SourceFileOut)
def patch_source(request: Request, source_id: uuid.UUID, body: SourceFilePatch):
    try:
        return _out(_service(request).rename(str(source_id), body.display_name, body.folder))
    except SourceFileError as exc:
        _error(exc)


@router.delete("/{source_id}", status_code=204)
def delete_source(request: Request, source_id: uuid.UUID):
    try:
        _service(request).delete(str(source_id))
    except SourceFileError as exc:
        _error(exc)
    return Response(status_code=204)


@router.post("/{source_id}/retry", response_model=SourceFileOut)
def retry(request: Request, source_id: uuid.UUID):
    status = request.app.state.container.model_runtime.status()
    model = status.active_model
    try:
        return _out(_service(request).retry(str(source_id), profile_id=model.id if model else None,
                                        profile_revision=model.revision if model else None))
    except SourceFileError as exc:
        _error(exc)
