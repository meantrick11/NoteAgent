import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


class NotePathError(ValueError):
    """Raised when a note path would escape the notes root or is invalid."""


class FileNoteRepository:
    """Read and write Markdown notes under a single directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[str]:
        """Return sorted file names in the notes directory."""
        names = sorted(path.name for path in self.root.iterdir() if path.is_file())
        _logger.info("note list count=%d", len(names))
        return names

    def read(self, file_name: str) -> str:
        """Return UTF-8 text of an existing note."""
        path = self._resolve(file_name)
        if not path.exists():
            _logger.warning("note read missing file=%s", file_name)
            raise FileNotFoundError(file_name)
        text = path.read_text(encoding="utf-8")
        _logger.info("note read file=%s chars=%d", file_name, len(text))
        return text

    def create(self, file_name: str, title: str) -> str:
        """Create a new .md note with an H1 title. Returns the stored file name."""
        file_name = self._ensure_markdown_name(file_name)
        path = self._resolve(file_name)
        if path.exists():
            _logger.warning("note create exists file=%s", file_name)
            raise FileExistsError(file_name)
        path.write_text(f"# {title}\n\n", encoding="utf-8")
        _logger.info("note create file=%s", file_name)
        return file_name

    def write(self, file_name: str, content: str, *, append: bool = True) -> None:
        """Append or overwrite an existing note. Empty content is rejected."""
        path = self._resolve(file_name)
        if not content:
            raise ValueError("no content given")
        if not path.exists():
            _logger.warning("note write missing file=%s", file_name)
            raise FileNotFoundError(file_name)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        _logger.info("note write file=%s mode=%s chars=%d preview=%.120s",
            file_name,
            mode,
            len(content),
            content,
        )

    def delete(self, file_name: str) -> None:
        """Remove an existing note file. Missing files raise FileNotFoundError."""
        file_name = self._ensure_markdown_name(file_name)
        path = self._resolve(file_name)
        if not path.exists():
            _logger.warning("note delete missing file=%s", file_name)
            raise FileNotFoundError(file_name)
        path.unlink()
        _logger.info("note delete file=%s", file_name)

    def exists(self, file_name: str) -> bool:
        """True if a note with this name exists under the root."""
        try:
            return self._resolve(self._ensure_markdown_name(file_name)).exists()
        except NotePathError:
            return False

    def _ensure_markdown_name(self, file_name: str) -> str:
        """Append .md when the caller omitted the extension."""
        if not file_name.endswith(".md"):
            return f"{file_name}.md"
        return file_name

    def _resolve(self, file_name: str) -> Path:
        """Map a bare file name to a path inside root; reject traversal and nesting."""
        if not file_name or not file_name.strip():
            raise NotePathError("no target file given")
        candidate = Path(file_name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise NotePathError("path escapes notes directory")
        if candidate.parent != Path("."):
            raise NotePathError("nested paths are not allowed")
        resolved = (self.root / candidate.name).resolve()
        if not resolved.is_relative_to(self.root):
            raise NotePathError("path escapes notes directory")
        return resolved
