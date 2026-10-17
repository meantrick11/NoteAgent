from datetime import datetime
from pydantic import BaseModel


class SourceFileOut(BaseModel):
    id: str
    original_filename: str
    storage_path: str
    display_name: str
    folder: str
    media_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime


class SourceFilePatch(BaseModel):
    display_name: str | None = None
    folder: str | None = None


class FolderIn(BaseModel):
    name: str


class FolderRenameIn(BaseModel):
    name: str
