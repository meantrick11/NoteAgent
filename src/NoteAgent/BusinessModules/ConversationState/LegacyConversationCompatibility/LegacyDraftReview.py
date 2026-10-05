"""Compatibility review for old conversations and isolated diagnostic containers."""

import logging
from pathlib import Path
from NoteAgent.BusinessModules.ConversationState.PendingDrafts import DraftStore, WRITE_ACTIONS, markdown_name
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository, NotePathError
from NoteAgent.BusinessModules.NoteRetrieval.NoteRetrievalService import RetrievalService

_logger = logging.getLogger(__name__)

def commit_review(
    notes: FileNoteRepository,
    store: DraftStore,
    thread_id: str,
    action: str,
    write_action: str | None = None,
    file_name: str | None = None,
    retrieval: RetrievalService | None = None,
) -> dict:
    """Apply or discard the pending draft. Writes happen only here, not in tools.

    After a successful disk write, sync Chroma for that file. Index failures are
    logged and do not roll back the Markdown or change the written response.
    """
    draft = store.pop(thread_id)
    if draft is None:
        return {"error": "no pending draft"}

    if action == "reject":
        _logger.info("draft rejected thread=%s", thread_id)
        return {"status": "rejected"}

    if action == "override":
        if write_action not in WRITE_ACTIONS or not file_name:
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
    except (OSError, ValueError) as exc:
        # 写盘失败（含 PermissionError 等 OSError）时必须把唯一待审草稿放回数据库，
        # 否则用户既没写成文件，也失去了重新审批的机会。
        store.put(thread_id, draft)
        _logger.warning(
            "draft write failed thread=%s action=%s file=%s error=%s",
            thread_id,
            target_action,
            target_name,
            exc,
        )
        return {"error": str(exc)}

    _logger.info(
        "draft committed thread=%s action=%s file=%s",
        thread_id,
        target_action,
        target_name,
    )
    _sync_index(retrieval, target_action, target_name)
    return {"status": "written", "action": target_action, "file_name": target_name}


def _sync_index(
    retrieval: RetrievalService | None,
    action: str,
    file_name: str,
) -> None:
    """Mirror one approved file into Chroma. Never raises to the review caller."""
    if retrieval is None:
        return
    try:
        if action == "delete":
            retrieval.delete_note(file_name)
            return
        chunks = retrieval.index_note(file_name)
        _logger.info("draft indexed file=%s chunks=%d", file_name, chunks)
    except Exception:
        _logger.exception("draft index failed action=%s file=%s", action, file_name)


def _write_draft(
    notes: FileNoteRepository,
    action: str,
    file_name: str,
    content: str,
) -> None:
    """Apply the approved action to disk. Does not call the LLM."""
    file_name = markdown_name(file_name)
    if action == "create":
        title = Path(file_name).stem
        notes.create(file_name, title)
        notes.write(file_name, content, append=True)
        return
    if action == "append":
        notes.write(file_name, content, append=True)
        return
    if action == "replace":
        notes.write(file_name, content, append=False)
        return
    if action == "delete":
        notes.delete(file_name)
        return
    raise ValueError(f"unknown write action {action}")
