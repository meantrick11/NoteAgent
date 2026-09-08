import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from noteagent.notes.repository import FileNoteRepository, NotePathError
from noteagent.notes.schemas import (
    FolderCreateIn,
    FolderDeleteOut,
    FolderOut,
    FolderRenameIn,
    FolderRenameOut,
    NoteContentOut,
    NoteCreateIn,
    NoteFileOut,
    NoteMoveIn,
    NotesListOut,
    NoteWriteIn,
    NoteWriteOut,
)
from noteagent.retrieval.service import RetrievalService

_logger = logging.getLogger(__name__)

router = APIRouter()


def _notes(request: Request) -> FileNoteRepository:
    return request.app.state.container.notes


def _retrieval(request: Request) -> RetrievalService | None:
    return getattr(request.app.state.container, "retrieval", None)


def _raise_notes_error(exc: Exception) -> None:
    """Map note-path and file errors to 400/404/409; re-raise anything else."""
    if isinstance(exc, NotePathError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, FileExistsError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _try_index(retrieval: RetrievalService | None, file_name: str) -> bool:
    """Rebuild Chroma for one file; log failures and leave the Markdown unchanged."""
    if retrieval is None:
        return False
    try:
        retrieval.index_note(file_name)
        return retrieval.is_indexed(file_name)
    except Exception:
        _logger.exception("notes index failed file=%s", file_name)
        return False


def _try_delete_index(retrieval: RetrievalService | None, file_name: str) -> None:
    """Drop this file's vectors; log failures without failing the HTTP write."""
    if retrieval is None:
        return
    try:
        retrieval.delete_note(file_name)
    except Exception:
        _logger.exception("notes vector delete failed file=%s", file_name)


def _indexed(retrieval: RetrievalService | None, file_name: str) -> bool:
    """True if Chroma has at least one chunk for this path; False on missing retrieval or errors."""
    if retrieval is None:
        return False
    try:
        return retrieval.is_indexed(file_name)
    except Exception:
        _logger.exception("notes indexed check failed file=%s", file_name)
        return False


def _folder_of(file_name: str) -> str:
    if "/" not in file_name:
        return ""
    return file_name.rsplit("/", 1)[0]


@router.get("/notes", response_model=NotesListOut)
async def list_notes(request: Request) -> NotesListOut:
    """List folders and notes with mtime and index status. No notes table."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    files = [
        NoteFileOut(
            file_name=file_name,
            folder=_folder_of(file_name),
            mtime=notes.mtime(file_name),
            indexed=_indexed(retrieval, file_name),
        )
        for file_name in notes.list_notes()
    ]
    folders = notes.list_folders()
    _logger.info("notes http list files=%d folders=%d", len(files), len(folders))
    return NotesListOut(files=files, folders=folders)


@router.post("/notes", response_model=NoteWriteOut)
async def create_note(body: NoteCreateIn, request: Request) -> NoteWriteOut:
    """Create a note then index it. Documents human-write path, not chat review."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        name = notes.normalize(body.file_name)
        name = notes.create(name, Path(name).stem)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    indexed = _try_index(retrieval, name)
    _logger.info("notes http create file=%s indexed=%s", name, indexed)
    return NoteWriteOut(file_name=name, indexed=indexed)


@router.post("/notes/folders", response_model=FolderOut)
async def create_folder(body: FolderCreateIn, request: Request) -> FolderOut:
    """Create an empty one-level folder."""
    try:
        name = _notes(request).create_folder(body.name)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    _logger.info("notes http folder create name=%s", name)
    return FolderOut(name=name)


@router.post("/notes/folders/rename", response_model=FolderRenameOut)
async def rename_folder(body: FolderRenameIn, request: Request) -> FolderRenameOut:
    """Rename a real folder and reindex every note under the new path."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        old, new, pairs = notes.rename_folder(body.from_path, body.to_path)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    for src, dest in pairs:
        if src != dest:
            _try_delete_index(retrieval, src)
        _try_index(retrieval, dest)
    _logger.info("notes http folder rename from=%s to=%s files=%d", old, new, len(pairs))
    return FolderRenameOut(from_name=old, to_name=new, files=[dest for _, dest in pairs])


@router.delete("/notes/folders/{name}", response_model=FolderDeleteOut)
async def delete_folder(name: str, request: Request) -> FolderDeleteOut:
    """Delete a real folder, its notes, and their vectors. Must be before /notes/{path}."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        deleted = notes.delete_folder(name)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    for file_name in deleted:
        _try_delete_index(retrieval, file_name)
    _logger.info("notes http folder delete name=%s files=%d", name, len(deleted))
    return FolderDeleteOut(name=name, deleted=deleted)


@router.post("/notes/move", response_model=NoteWriteOut)
async def move_note(body: NoteMoveIn, request: Request) -> NoteWriteOut:
    """Move a note and reindex under the new relative path."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        src = notes.normalize(body.from_path)
        dest = notes.move(body.from_path, body.to_path)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    if src != dest:
        _try_delete_index(retrieval, src)
    indexed = _try_index(retrieval, dest)
    _logger.info("notes http move from=%s to=%s indexed=%s", src, dest, indexed)
    return NoteWriteOut(file_name=dest, indexed=indexed)


@router.post("/notes/{file_name:path}/index", response_model=NoteWriteOut)
async def index_note(file_name: str, request: Request) -> NoteWriteOut:
    """Rebuild vectors for an existing note without changing the Markdown file."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        name = notes.normalize(file_name)
        if not notes.exists(name):
            raise FileNotFoundError(name)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    indexed = _try_index(retrieval, name)
    _logger.info("notes http index file=%s indexed=%s", name, indexed)
    return NoteWriteOut(file_name=name, indexed=indexed)


@router.get("/notes/{file_name:path}", response_model=NoteContentOut)
async def read_note(file_name: str, request: Request) -> NoteContentOut:
    """Return Markdown text of one note."""
    notes = _notes(request)
    try:
        content = notes.read(file_name)
        name = notes.normalize(file_name)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    return NoteContentOut(file_name=name, content=content)


@router.put("/notes/{file_name:path}", response_model=NoteWriteOut)
async def save_note(file_name: str, body: NoteWriteIn, request: Request) -> NoteWriteOut:
    """Overwrite Markdown (user save = review) then rebuild vectors."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        name = notes.normalize(file_name)
        notes.write(name, body.content, append=False)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    indexed = _try_index(retrieval, name)
    _logger.info("notes http save file=%s indexed=%s", name, indexed)
    return NoteWriteOut(file_name=name, indexed=indexed)


@router.delete("/notes/{file_name:path}", response_model=NoteWriteOut)
async def delete_note(file_name: str, request: Request) -> NoteWriteOut:
    """Delete the Markdown file and drop its vectors."""
    notes = _notes(request)
    retrieval = _retrieval(request)
    try:
        name = notes.normalize(file_name)
        notes.delete(name)
    except Exception as exc:
        _raise_notes_error(exc)
        raise
    _try_delete_index(retrieval, name)
    _logger.info("notes http delete file=%s", name)
    return NoteWriteOut(file_name=name, indexed=False)
