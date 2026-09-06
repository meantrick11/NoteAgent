import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


class NotePathError(ValueError):
    """Raised when a note path would escape the notes root or is invalid."""


class FileNoteRepository:
    """Read and write Markdown notes under a single directory.

    Relative paths may be a root file (`Go.md`) or one folder (`Python/GIL.md`).
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[str]:
        """Return sorted relative paths of `.md` files at root and one level down."""
        names: list[str] = []
        for path in self.root.iterdir():
            if path.is_file() and path.suffix == ".md":
                names.append(path.name)
            elif path.is_dir() and not path.name.startswith("."):
                for child in path.iterdir():
                    if child.is_file() and child.suffix == ".md":
                        names.append(f"{path.name}/{child.name}")
        names.sort()
        _logger.info("note list count=%d", len(names))
        return names

    def list_folders(self) -> list[str]:
        """Return sorted one-level folder names under the notes root."""
        names = sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )
        return names

    def create_folder(self, name: str) -> str:
        """Create an empty one-level folder. Raises FileExistsError if present."""
        folder = self._normalize_folder(name)
        path = (self.root / folder).resolve()
        if not path.is_relative_to(self.root):
            raise NotePathError("path escapes notes directory")
        if path.exists():
            raise FileExistsError(folder)
        path.mkdir()
        _logger.info("note folder create name=%s", folder)
        return folder

    def rename_folder(self, src: str, dest: str) -> tuple[str, str, list[tuple[str, str]]]:
        """Rename a one-level folder. Returns old name, new name, and (old, new) note paths."""
        old = self._normalize_folder(src)
        new = self._normalize_folder(dest)
        old_path = (self.root / old).resolve()
        new_path = (self.root / new).resolve()
        if not old_path.is_relative_to(self.root) or not new_path.is_relative_to(self.root):
            raise NotePathError("path escapes notes directory")
        if not old_path.is_dir():
            raise FileNotFoundError(old)
        if old != new and new_path.exists():
            raise FileExistsError(new)
        pairs = [
            (f"{old}/{child.name}", f"{new}/{child.name}")
            for child in sorted(old_path.iterdir())
            if child.is_file() and child.suffix == ".md"
        ]
        if old != new:
            old_path.rename(new_path)
        _logger.info("note folder rename from=%s to=%s files=%d", old, new, len(pairs))
        return old, new, pairs

    def delete_folder(self, name: str) -> list[str]:
        """Delete a one-level folder and every .md inside it. Returns deleted relative paths."""
        folder = self._normalize_folder(name)
        path = (self.root / folder).resolve()
        if not path.is_relative_to(self.root):
            raise NotePathError("path escapes notes directory")
        if not path.is_dir():
            raise FileNotFoundError(folder)
        deleted = [
            f"{folder}/{child.name}"
            for child in sorted(path.iterdir())
            if child.is_file() and child.suffix == ".md"
        ]
        for rel in deleted:
            self.delete(rel)
        path.rmdir()
        _logger.info("note folder delete name=%s files=%d", folder, len(deleted))
        return deleted

    def move(self, src: str, dest: str) -> str:
        """Rename/move a note. Dest must not already exist."""
        src_rel = self._normalize_note(src)
        dest_rel = self._normalize_note(dest)
        src_path = self._resolve(src_rel)
        dest_path = self._resolve(dest_rel)
        if not src_path.exists():
            raise FileNotFoundError(src_rel)
        if dest_path.exists():
            raise FileExistsError(dest_rel)
        dest_path.parent.mkdir(exist_ok=True)
        src_path.rename(dest_path)
        _logger.info("note move from=%s to=%s", src_rel, dest_rel)
        return dest_rel

    def mtime(self, file_name: str) -> float:
        """POSIX mtime of an existing note."""
        path = self._resolve(file_name)
        if not path.exists():
            raise FileNotFoundError(self._normalize_note(file_name))
        return path.stat().st_mtime

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
        """Create a new .md note with an H1 title. Returns the stored relative path."""
        file_name = self._normalize_note(file_name)
        path = self._resolve(file_name)
        if path.exists():
            _logger.warning("note create exists file=%s", file_name)
            raise FileExistsError(file_name)
        path.parent.mkdir(exist_ok=True)
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
        _logger.info(
            "note write file=%s mode=%s chars=%d preview=%.120s",
            file_name,
            mode,
            len(content),
            content,
        )

    def delete(self, file_name: str) -> None:
        """Remove an existing note file. Missing files raise FileNotFoundError."""
        file_name = self._normalize_note(file_name)
        path = self._resolve(file_name)
        if not path.exists():
            _logger.warning("note delete missing file=%s", file_name)
            raise FileNotFoundError(file_name)
        path.unlink()
        _logger.info("note delete file=%s", file_name)

    def exists(self, file_name: str) -> bool:
        """True if a note with this relative path exists under the root."""
        try:
            return self._resolve(file_name).exists()
        except NotePathError:
            return False

    def normalize(self, file_name: str) -> str:
        """Return the stored relative path (`Folder/Note.md` or `Note.md`)."""
        return self._normalize_note(file_name)

    def _ensure_markdown_name(self, file_name: str) -> str:
        """Append .md when the caller omitted the extension."""
        return self._normalize_note(file_name)

    def _normalize_folder(self, name: str) -> str:
        raw = (name or "").replace("\\", "/").strip().strip("/")
        if not raw:
            raise NotePathError("no target folder given")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
            raise NotePathError("nested paths are not allowed")
        folder = candidate.parts[0]
        if folder in (".", "..") or folder.endswith(".md"):
            raise NotePathError("invalid folder name")
        return folder

    def _normalize_note(self, file_name: str) -> str:
        if not file_name or not str(file_name).strip():
            raise NotePathError("no target file given")
        raw = file_name.replace("\\", "/").strip()
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise NotePathError("path escapes notes directory")
        parts = candidate.parts
        if len(parts) not in (1, 2):
            raise NotePathError("nested paths are not allowed")
        if any(part in ("", ".", "..") for part in parts):
            raise NotePathError("path escapes notes directory")
        last = parts[-1]
        if not last.endswith(".md"):
            last = f"{last}.md"
        if len(parts) == 1:
            return last
        folder = parts[0]
        if folder.endswith(".md"):
            raise NotePathError("invalid folder name")
        return f"{folder}/{last}"

    def _resolve(self, file_name: str) -> Path:
        """Map a relative note path inside root; reject traversal and two-level nests."""
        rel = self._normalize_note(file_name)
        resolved = (self.root / Path(rel)).resolve()
        if not resolved.is_relative_to(self.root):
            raise NotePathError("path escapes notes directory")
        return resolved
