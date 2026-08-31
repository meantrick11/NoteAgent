import logging
from contextvars import ContextVar
from dataclasses import dataclass, field

from noteagent.notes.repository import FileNoteRepository, NotePathError

_logger = logging.getLogger(__name__)

current_thread_id: ContextVar[str] = ContextVar("noteagent_thread_id", default="")
current_turn_id: ContextVar[str] = ContextVar("noteagent_turn_id", default="")

#获取对应的笔记文件
def markdown_name(file_name: str) -> str:
    """Ensure a notes file name ends with .md."""
    if not file_name.endswith(".md"):
        return f"{file_name}.md"
    return file_name

#笔记草稿类
@dataclass
class NoteDraft:
    """Pending note proposal waiting for human approval."""

    action: str
    file_name: str
    content: str
    reason: str = ""
    similar: list[str] = field(default_factory=list)
    existing_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """JSON payload for the SSE draft event and the frontend card."""
        return {
            "action": self.action,
            "file_name": self.file_name,
            "content": self.content,
            "reason": self.reason,
            "similar": self.similar,
            "existing_files": self.existing_files,
        }


class DraftStore:
    """In-memory pending draft per chat thread. Lost on process restart."""

    def __init__(self):
        self._pending: dict[str, NoteDraft] = {}

    def put(self, thread_id: str, draft: NoteDraft) -> None:
        _logger.info(
            "draft pending thread=%s action=%s file=%s",
            thread_id,
            draft.action,
            draft.file_name,
        )
        self._pending[thread_id] = draft

    def get(self, thread_id: str) -> NoteDraft | None:
        return self._pending.get(thread_id)

    def pop(self, thread_id: str) -> NoteDraft | None:
        return self._pending.pop(thread_id, None)

##如果用户确认提交对应的笔记，此函数表示确认然后执行write到对应文件的
def commit_review(
    notes: FileNoteRepository,
    store: DraftStore,
    thread_id: str,
    action: str,
    write_action: str | None = None,
    file_name: str | None = None,
) -> dict:
    """Apply or discard the pending draft. Writes happen only here, not in tools."""
    draft = store.pop(thread_id)
    if draft is None:
        return {"error": "no pending draft"}

    if action == "reject":
        _logger.info("draft rejected thread=%s", thread_id)
        return {"status": "rejected"}

    if action == "override":
        if write_action not in ("append", "create") or not file_name:
            store.put(thread_id, draft)
            return {"error": "override requires write_action and file_name"}
        target_action = write_action
        target_name = markdown_name(file_name)
    elif action == "approve":
        target_action = draft.action
        target_name = draft.file_name
    else:
        store.put(thread_id, draft)
        return {"error": f"unknown action {action}"}

    try:
        _write_draft(notes, target_action, target_name, draft.content)
    except (FileNotFoundError, FileExistsError, NotePathError, ValueError) as exc:
        store.put(thread_id, draft)
        _logger.warning("draft write failed thread=%s error=%s", thread_id, exc)
        return {"error": str(exc)}

    _logger.info(
        "draft committed thread=%s action=%s file=%s",
        thread_id,
        target_action,
        target_name,
    )
    return {"status": "written", "action": target_action, "file_name": target_name}

# 撰写草稿
def _write_draft(
    notes: FileNoteRepository,
    action: str,
    file_name: str,
    content: str,
) -> None:
    """Create and/or append the approved markdown. Does not call the LLM."""
    file_name = markdown_name(file_name)
    if action == "create":
        title = file_name[:-3]
        notes.create(file_name, title)
        notes.write(file_name, content, append=True)
        return
    if action == "append":
        notes.write(file_name, content, append=True)
        return
    raise ValueError(f"unknown write action {action}")
