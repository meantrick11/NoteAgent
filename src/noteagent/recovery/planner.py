"""Pure recovery preview: which files a rollback would touch, and what conflicts.

The planner is a pure function over recorded data (it opens no sessions and writes
nothing), so it can be unit-tested exactly and reused by the coordinator. It inverts
only the *owned* mutations of the current conversation after the boundary; any later
mutation by another origin that touches an affected path — including one that wrote the
same bytes back (ABA) — makes the whole plan un-appliable rather than silently
overwriting someone else's work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class MutationView:
    """One ledger entry, as read by the planner."""

    operation_id: str
    origin_kind: str  # conversation | library | external
    kind: str
    paths: list[str]
    before_hashes: dict[str, str]
    before_commit: str | None = None
    after_commit: str | None = None
    workspace_seq: int = 0
    conversation_id: str | None = None


@dataclass(slots=True)
class FileChange:
    """One file the plan would put back (or delete, when it did not exist before)."""

    path: str
    action: str  # restore | delete
    target_hash: str | None
    current_hash: str | None


@dataclass(slots=True)
class FolderChange:
    """One folder the plan would create or delete."""

    path: str
    action: str  # create | delete


@dataclass(slots=True)
class Conflict:
    """A reason the whole plan cannot be applied."""

    path: str
    reason: str


@dataclass(slots=True)
class RestorePlan:
    """The preview returned to the client before any recovery starts."""

    conversation_id: str
    branch_id: str
    state_revision: int
    workspace_seq: int
    file_changes: list[FileChange] = field(default_factory=list)
    folder_changes: list[FolderChange] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    affected_messages: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    content_digest: str = ""
    boundary: dict = field(default_factory=dict)
    expires_at: str | None = None

    @property
    def can_apply(self) -> bool:
        return not self.conflicts

    def as_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "branch_id": self.branch_id,
            "state_revision": self.state_revision,
            "workspace_seq": self.workspace_seq,
            "can_apply": self.can_apply,
            "requires_confirmation": self.requires_confirmation,
            "file_changes": [asdict(c) for c in self.file_changes],
            "folder_changes": [asdict(c) for c in self.folder_changes],
            "conflicts": [asdict(c) for c in self.conflicts],
            "affected_messages": list(self.affected_messages),
            "content_digest": self.content_digest,
            "expires_at": self.expires_at,
        }


def _digest(changes: list[FileChange], folders: list[FolderChange]) -> str:
    payload = json.dumps(
        {
            "files": sorted((c.path, c.action, c.target_hash or "") for c in changes),
            "folders": sorted((c.path, c.action) for c in folders),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def plan(
    *,
    conversation_id: str,
    branch_id: str,
    state_revision: int,
    workspace_seq: int,
    boundary: dict,
    owned_mutations: list[MutationView],
    later_mutations: list[MutationView],
    current_manifest: dict[str, str | None],
    affected_messages: list[str] | None = None,
    expires_at: str | None = None,
) -> RestorePlan:
    """Build a :class:`RestorePlan`; never mutates any file, index or head."""
    result = RestorePlan(
        conversation_id=conversation_id,
        branch_id=branch_id,
        state_revision=state_revision,
        workspace_seq=workspace_seq,
        boundary=dict(boundary),
        affected_messages=list(affected_messages or []),
        expires_at=expires_at,
    )

    if boundary.get("recoverable") is False:
        result.conflicts.append(
            Conflict("", "history_not_recoverable")
        )
        return result

    # Rebuild the target file state by inverting owned operations, newest first.
    targets: dict[str, str | None] = dict(current_manifest)
    affected_files: set[str] = set()
    folder_changes: list[FolderChange] = []
    for mutation in sorted(owned_mutations, key=lambda m: m.workspace_seq, reverse=True):
        if mutation.kind in ("folder_create", "folder_delete", "folder_rename"):
            for path in mutation.paths:
                if not path.endswith("/"):
                    continue
                if mutation.kind == "folder_create":
                    folder_changes.append(FolderChange(path, "delete"))
                elif mutation.kind == "folder_delete":
                    folder_changes.append(FolderChange(path, "create"))
            continue
        for path in mutation.paths:
            affected_files.add(path)
            targets[path] = mutation.before_hashes.get(path)

    # Any later mutation touching an affected path (or inside an affected folder) is a
    # shared change -> conflict, even when it wrote the same bytes back (ABA).
    affected_folders = {change.path for change in folder_changes}
    for mutation in later_mutations:
        for path in mutation.paths:
            if path in affected_files or any(path.startswith(f) for f in affected_folders):
                result.conflicts.append(
                    Conflict(path, f"changed after the boundary by {mutation.origin_kind}")
                )

    # Untracked content appearing inside a folder we would touch is also a conflict.
    boundary_files = boundary.get("files") or {}
    for folder in affected_folders:
        for path in current_manifest:
            if path.startswith(folder) and path not in boundary_files:
                result.conflicts.append(Conflict(path, "untracked file inside a restored folder"))

    for path in sorted(affected_files):
        target = targets.get(path)
        current = current_manifest.get(path)
        if target is None and current is None:
            continue
        result.file_changes.append(
            FileChange(
                path=path,
                action="restore" if target is not None else "delete",
                target_hash=target,
                current_hash=current,
            )
        )

    result.folder_changes = folder_changes
    result.requires_confirmation = bool(result.file_changes or result.folder_changes)
    result.content_digest = _digest(result.file_changes, result.folder_changes)
    return result
