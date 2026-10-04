"""Shadow Git note versions in an isolated, bare repository.

The version store owns a bare repository that is *separate* from the notes directory
and from the code repository's ``.git``. It never writes into the notes tree and never
touches the code repo's HEAD or index: blobs are built from raw file bytes through
plumbing commands (``hash-object`` / ``mktree`` / ``commit-tree``) with ``argv`` and
``shell=False``, so CRLF, Chinese text and empty files round-trip exactly.

Two identities make a commit recoverable: a normal line ref (``refs/heads/notes``)
and one retention ref per operation (``refs/versions/<operation_id>``), so a commit
that Git accepted but the DB never bound can still be found. A directory manifest —
including empty folders, which a Git tree cannot represent — is stored as a blob the
commit points at through ``refs/manifests/<commit>``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_SHA = re.compile(r"^[0-9a-f]{40}$")
_NOTES_LINE_REF = "refs/heads/notes"
_DEFAULT_AUTHOR = ("noteagent", "noteagent@local")


class NoteVersionError(RuntimeError):
    """A path, commit or repository state is not usable for a version operation."""


@dataclass(slots=True)
class Snapshot:
    """One version commit plus the paths that changed relative to its parent."""

    commit: str
    parent: str | None
    changed_paths: list[str] = field(default_factory=list)
    reused: bool = False


def _validate_path(path: str) -> str:
    """Return a safe relative posix path; reject traversal, absolute, hidden, ref syntax."""
    if not path:
        raise NoteVersionError("no path given")
    normalized = str(path).replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or ":" in normalized:
        raise NoteVersionError(f"unsafe path: {path!r}")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise NoteVersionError(f"unsafe path: {path!r}")
    if any(part.startswith(".") for part in parts):
        raise NoteVersionError(f"hidden path not tracked: {path!r}")
    return normalized


def _validate_commit(commit: str) -> str:
    """Accept only a full object id; a user string can never become an arbitrary ref."""
    if not commit or not _SHA.match(commit):
        raise NoteVersionError(f"not a commit id: {commit!r}")
    return commit


class NoteVersionStore:
    """Bare-repo version storage for one notes directory."""

    def __init__(self, repo_dir: Path, notes_dir: Path) -> None:
        self.repo_dir = Path(repo_dir)
        self.notes_dir = Path(notes_dir).resolve()
        if self.repo_dir.resolve() == self.notes_dir or self.repo_dir.resolve().is_relative_to(self.notes_dir):
            raise NoteVersionError("history directory must not live inside the notes directory")
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_repo()

    # ---- git plumbing -----------------------------------------------------

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_DIR"] = str(self.repo_dir)
        env["GIT_AUTHOR_NAME"], env["GIT_AUTHOR_EMAIL"] = _DEFAULT_AUTHOR
        env["GIT_COMMITTER_NAME"], env["GIT_COMMITTER_EMAIL"] = _DEFAULT_AUTHOR
        return env

    def _git(self, *args: str, input: bytes | None = None) -> bytes:
        """Run one git command with argv (never a shell) and return stdout bytes."""
        result = subprocess.run(
            ["git", *args],
            input=input,
            capture_output=True,
            env=self._env(),
            shell=False,
        )
        if result.returncode != 0:
            raise NoteVersionError(
                f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace').strip()}"
            )
        return result.stdout

    def _ensure_repo(self) -> None:
        if not (self.repo_dir / "HEAD").exists():
            self._git("init", "--bare", "-q", str(self.repo_dir))
            logger.info("shadow note repo initialized dir=%s", self.repo_dir)

    def _hash_blob(self, data: bytes) -> str:
        return self._git("hash-object", "-w", "-t", "blob", "--stdin", input=data).decode().strip()

    def _mktree(self, entries: list[tuple[str, str, str]]) -> str:
        """Build a tree from (mode, type, sha, name); names are already validated."""
        lines = b"".join(
            f"{mode} {kind} {sha}\t{name}\n".encode("utf-8")
            for mode, kind, sha, name in entries
        )
        return self._git("mktree", input=lines).decode().strip()

    def _commit_tree(self, tree: str, parent: str | None, message: str) -> str:
        args = ["commit-tree", tree]
        if parent:
            args += ["-p", parent]
        args += ["-m", message]
        return self._git(*args).decode().strip()

    def _rev_parse(self, expression: str) -> str | None:
        try:
            return self._git("rev-parse", "--verify", "-q", expression).decode().strip() or None
        except NoteVersionError:
            return None

    # ---- scanning ---------------------------------------------------------

    def _scan(self) -> tuple[dict[str, bytes], list[str]]:
        """Read every tracked file's raw bytes plus the folder list (empty ones included)."""
        files: dict[str, bytes] = {}
        folders: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(self.notes_dir, followlinks=False):
            # Never follow or track symlinked/junction directories or the bare repo.
            dirnames[:] = sorted(
                name for name in dirnames
                if not name.startswith(".") and not os.path.islink(os.path.join(dirpath, name))
            )
            rel_dir = Path(dirpath).relative_to(self.notes_dir)
            for name in dirnames:
                rel = (rel_dir / name).as_posix()
                if rel and rel != ".":
                    folders.add(rel)
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    continue
                rel = (rel_dir / name).as_posix()
                files[_validate_path(rel)] = Path(full).read_bytes()
        return files, sorted(folders)

    def _build_tree(self, files: dict[str, bytes]) -> tuple[str, dict[str, str]]:
        """Build nested trees; returns (root tree sha, path -> blob sha)."""
        hashes = {path: self._hash_blob(data) for path, data in files.items()}
        root: list[tuple[str, str, str, str]] = []
        by_folder: dict[str, list[tuple[str, str, str, str]]] = {}
        for path, sha in sorted(hashes.items()):
            parts = path.split("/")
            if len(parts) == 1:
                root.append(("100644", "blob", sha, parts[0]))
            else:
                by_folder.setdefault(parts[0], []).append(
                    ("100644", "blob", sha, "/".join(parts[1:]))
                )
        for folder, entries in by_folder.items():
            subtree = self._mktree(sorted(entries, key=lambda e: e[3]))
            root.append(("040000", "tree", subtree, folder))
        return self._mktree(sorted(root, key=lambda e: e[3])), hashes

    def _store_manifest(self, commit: str, files: dict[str, str], folders: list[str]) -> None:
        manifest = json.dumps(
            {"files": files, "folders": folders}, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        blob = self._hash_blob(manifest)
        self._git("update-ref", f"refs/manifests/{commit}", blob)

    # ---- public API -------------------------------------------------------

    def init(self) -> str:
        """Create the initial version from the current notes; reuse if nothing changed."""
        existing = self._rev_parse(_NOTES_LINE_REF)
        snapshot = self.snapshot(existing, operation_id="init")
        return snapshot.commit

    def snapshot(self, parent_commit: str | None, operation_id: str) -> Snapshot:
        """Write a version commit for the current notes and retain it under the op id."""
        parent = _validate_commit(parent_commit) if parent_commit else None
        files, folders = self._scan()
        tree, hashes = self._build_tree(files)

        if parent is not None:
            parent_tree = self._rev_parse(f"{parent}^{{tree}}")
            if parent_tree == tree:
                # Nothing changed: reuse the parent, never manufacture an empty commit.
                self._retain(operation_id, parent)
                return Snapshot(commit=parent, parent=parent, changed_paths=[], reused=True)
            changed = self._diff(parent, hashes, folders)
        else:
            changed = sorted(hashes)

        commit = self._commit_tree(tree, parent, f"snapshot {operation_id}")
        self._git("update-ref", _NOTES_LINE_REF, commit)
        self._store_manifest(commit, hashes, folders)
        self._retain(operation_id, commit)
        logger.info(
            "note snapshot commit=%s parent=%s changed=%d", commit, parent, len(changed)
        )
        return Snapshot(commit=commit, parent=parent, changed_paths=changed)

    def _retain(self, operation_id: str, commit: str) -> None:
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", str(operation_id))[:80] or "op"
        self._git("update-ref", f"refs/versions/{safe}", commit)

    def _diff(self, parent: str, hashes: dict[str, str], folders: list[str]) -> list[str]:
        """Paths whose blob changed plus added/removed paths, versus the parent tree."""
        parent_files = self.manifests(parent)
        changed = set()
        for path, sha in hashes.items():
            if parent_files.get(path) != sha:
                changed.add(path)
        for path in parent_files:
            if path not in hashes:
                changed.add(path)
        parent_folders = set(self.folders(parent))
        for folder in folders:
            if folder not in parent_folders:
                changed.add(folder)
        for folder in parent_folders:
            if folder not in folders:
                changed.add(folder)
        return sorted(changed)

    def manifests(self, commit: str) -> dict[str, str]:
        """path -> blob sha for a commit, from the retained manifest blob."""
        commit = _validate_commit(commit)
        blob = self._rev_parse(f"refs/manifests/{commit}")
        if blob is not None:
            data = self._git("cat-file", "blob", blob)
            return dict(json.loads(data.decode("utf-8")).get("files") or {})
        # Fallback: read the tree directly (e.g. commit created before manifests existed).
        return self._ls_tree(commit)

    def folders(self, commit: str) -> list[str]:
        commit = _validate_commit(commit)
        blob = self._rev_parse(f"refs/manifests/{commit}")
        if blob is not None:
            data = self._git("cat-file", "blob", blob)
            return list(json.loads(data.decode("utf-8")).get("folders") or [])
        return []

    def _ls_tree(self, commit: str) -> dict[str, str]:
        out = self._git("ls-tree", "-r", "-z", commit)
        files: dict[str, str] = {}
        for entry in out.split(b"\x00"):
            if not entry:
                continue
            meta, _, name = entry.decode("utf-8").partition("\t")
            parts = meta.split()
            files[name] = parts[2]
        return files

    def read_blob(self, commit: str, path: str) -> bytes | None:
        """Raw bytes of one path at one commit, or None when it does not exist."""
        commit = _validate_commit(commit)
        rel = _validate_path(path)
        expression = f"{commit}:{rel}"
        try:
            return self._git("cat-file", "blob", expression)
        except NoteVersionError:
            return None

    def resolve_ref(self, operation_id: str) -> str | None:
        """The commit a retained operation ref points at, if it exists."""
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", str(operation_id))[:80] or "op"
        return self._rev_parse(f"refs/versions/{safe}")
