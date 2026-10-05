import logging
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field

from NoteAgent.BusinessModules.ConversationState.LegacyConversationCompatibility.LegacyConversationStore import ConversationStore

_logger = logging.getLogger(__name__)

current_thread_id: ContextVar[str] = ContextVar("noteagent_thread_id", default="")
current_turn_id: ContextVar[str] = ContextVar("noteagent_turn_id", default="")


@dataclass
class DraftWorkspace:
    """A graph node's private draft; returned as state before the node completes."""

    thread_id: str
    payload: dict | None


current_draft_workspace: ContextVar[DraftWorkspace | None] = ContextVar(
    "noteagent_draft_workspace", default=None,
)

WRITE_ACTIONS = ("append", "create", "replace", "delete")


class ProposeNoteInput(BaseModel):
    """Arguments for propose_note. Sent to the model via bind_tools JSON schema."""

    action: Literal["append", "create", "replace", "delete"] = Field(
        description=(
            "append 往已有文件末尾加新内容；create 新建文件；"
            "replace 用完整新正文覆盖已有文件；delete 删除已有文件。"
            "新知识默认 append 或 create，不要用 replace。"
        )
    )
    file_name: str = Field(description="笔记相对路径，如 Backtracking.md 或 Python/GIL.md")
    content: str = Field(
        default="",
        description=(
            "按用户材料组织的 Markdown 正文：可段落。"
            "材料已有章节标题时须含编号原文写入，按编号深度映射 ## / ### / ####；"
            "禁止自拟或合并标题。不是短要点清单。"
            "create/append 不要写一级标题；replace 须含读到的完整文件（含原有一级标题）。"
            "delete 时可空。"
            "代码用围栏；路径与命令用行内 code；备注用 > 引用。"
        )
    )
    reason: str = Field(default="", description="一句话说明为何归到这个文件")
    similar: str = Field(default="", description="逗号分隔的相近已有文件名，没有则空字符串")


#获取对应的笔记文件
def markdown_name(file_name: str) -> str:
    """Ensure a notes relative path ends with .md and uses /."""
    name = file_name.replace("\\", "/").strip()
    if not name.endswith(".md"):
        return f"{name}.md"
    return name

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

    @classmethod
    def from_dict(cls, data: dict) -> "NoteDraft":
        """Rebuild a draft from conversations.pending_draft JSON."""
        similar = data.get("similar") or []
        if isinstance(similar, str):
            similar = [item.strip() for item in similar.split(",") if item.strip()]
        existing = data.get("existing_files") or []
        return cls(
            action=data.get("action") or "",
            file_name=data.get("file_name") or "",
            content=data.get("content") or "",
            reason=data.get("reason") or "",
            similar=list(similar),
            existing_files=list(existing),
        )


class DraftStore:
    """One pending draft per conversation, stored on conversations.pending_draft."""

    def __init__(self, history: ConversationStore) -> None:
        self._history = history

    def put(self, thread_id: str, draft: NoteDraft) -> None:
        workspace = current_draft_workspace.get()
        if workspace is not None and workspace.thread_id == thread_id:
            workspace.payload = draft.as_dict()
            return
        _logger.info(
            "draft pending thread=%s action=%s file=%s",
            thread_id,
            draft.action,
            draft.file_name,
        )
        self._history.set_pending_draft(thread_id, draft.as_dict())

    def get(self, thread_id: str) -> NoteDraft | None:
        workspace = current_draft_workspace.get()
        payload = (workspace.payload if workspace is not None and workspace.thread_id == thread_id
                   else self._history.get_pending_draft(thread_id))
        if not payload:
            return None
        return NoteDraft.from_dict(payload)

    def pop(self, thread_id: str) -> NoteDraft | None:
        draft = self.get(thread_id)
        if draft is None:
            return None
        workspace = current_draft_workspace.get()
        if workspace is not None and workspace.thread_id == thread_id:
            workspace.payload = None
        else:
            self._history.clear_pending_draft(thread_id)
        return draft

    def update_content(self, thread_id: str, content: str) -> NoteDraft | None:
        """Rewrite only the pending draft's content; None when this thread has no draft.

        Editing a draft is not a write to disk: action, target file, reason and
        similar stay as proposed, and the notes repository is never touched.
        """
        if not content.strip():
            raise ValueError("no content given")
        draft = self.get(thread_id)
        if draft is None:
            return None
        updated = replace(draft, content=content)
        self.put(thread_id, updated)
        return updated

##如果用户确认提交对应的笔记，此函数表示确认然后执行write到对应文件的



# 撰写草稿
