from pydantic import BaseModel, Field


class NoteFileOut(BaseModel):
    """One note in the Documents list."""

    file_name: str
    folder: str
    mtime: float
    indexed: bool


class NotesListOut(BaseModel):
    """Folders plus files under notes/."""

    files: list[NoteFileOut]
    folders: list[str]


class NoteContentOut(BaseModel):
    """Full Markdown of one note."""

    file_name: str
    content: str


class NoteWriteIn(BaseModel):
    """Overwrite body for PUT /notes/{file_name}."""

    content: str


class NoteWriteOut(BaseModel):
    """Result of save, move, or delete-adjacent writes."""

    file_name: str
    indexed: bool


class FolderCreateIn(BaseModel):
    """POST /notes/folders."""

    name: str


class FolderOut(BaseModel):
    name: str


class NoteMoveIn(BaseModel):
    """POST /notes/move. JSON keys are from/to."""

    from_path: str = Field(alias="from")
    to_path: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class NoteCreateIn(BaseModel):
    """POST /notes. Relative path, optional .md suffix."""

    file_name: str


class FolderRenameIn(BaseModel):
    """POST /notes/folders/rename. JSON keys are from/to."""

    from_path: str = Field(alias="from")
    to_path: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class FolderRenameOut(BaseModel):
    from_name: str
    to_name: str
    files: list[str]


class FolderDeleteOut(BaseModel):
    name: str
    deleted: list[str]
