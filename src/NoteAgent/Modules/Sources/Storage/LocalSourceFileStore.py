"""Store source bytes under server-generated UUID names only."""
import os
import tempfile
import uuid
from pathlib import Path


class LocalSourceFileStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, source_id: str) -> Path:
        safe_id = str(uuid.UUID(source_id))
        return self.root / safe_id

    def write(self, source_id: str, data: bytes) -> None:
        path = self.path(source_id)
        handle = tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-", delete=False)
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, source_id: str) -> bytes:
        return self.path(source_id).read_bytes()

    def delete(self, source_id: str) -> None:
        self.path(source_id).unlink(missing_ok=True)
