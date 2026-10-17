from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from NoteAgent.Modules.Chat.Agent.Tools.ChatTools import build_chat_tools
from NoteAgent.Modules.Conversations.Service.PendingDrafts import current_thread_id
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from NoteAgent.Modules.Sources.Service.SourceFileAccess import authorized_source_ids, read_source_ids
from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService
from NoteAgent.Modules.Sources.Service.SourceFileWorker import SourceFileWorker
from NoteAgent.Common.Database.OrmBase import Base
from NoteAgent.Modules.Sources.Storage.LocalSourceFileStore import LocalSourceFileStore


class DraftCapture:
    draft = None

    def put(self, thread_id, draft):
        self.draft = draft


def test_agent_only_reads_authorized_files_and_draft_records_actual_use(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = SourceFileService(sessionmaker(engine), LocalSourceFileStore(tmp_path / "uploads"))
    source = service.upload("lesson.txt", b"content", content_type="text/plain")
    SourceFileWorker(service).run_once()
    drafts = DraftCapture()
    tools = {tool.name: tool for tool in build_chat_tools(FileNoteRepository(tmp_path / "notes"), None, drafts, source_files=service)}
    source_id = str(source.id)
    assert "error" in tools["read_source_file"].invoke({"source_id": source_id})
    allowed_token = authorized_source_ids.set({source_id})
    used_token = read_source_ids.set(set())
    thread_token = current_thread_id.set("thread")
    try:
        assert "error" in tools["propose_note"].invoke({
            "action": "create", "file_name": "lesson.md", "content": "# Lesson\n\ncontent",
            "source_file_ids": [source_id],
        })
        assert tools["read_source_file"].invoke({"source_id": source_id})["content"] == "[paragraph 1] content"
        result = tools["propose_note"].invoke({
            "action": "create", "file_name": "lesson.md", "content": "# Lesson\n\ncontent",
            "source_file_ids": [source_id],
        })
        assert result["status"] == "pending_review"
        assert drafts.draft.source_file_ids == [source_id]
        assert source_id in drafts.draft.content
        assert not (tmp_path / "notes" / "lesson.md").exists()
    finally:
        current_thread_id.reset(thread_token)
        read_source_ids.reset(used_token)
        authorized_source_ids.reset(allowed_token)
    service.delete(source_id)
    allowed_token = authorized_source_ids.set({source_id})
    try:
        assert "error" in tools["read_source_file"].invoke({"source_id": source_id})
    finally:
        authorized_source_ids.reset(allowed_token)


def test_append_preserves_approved_file_source_at_end(tmp_path):
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("lesson.md", "# Lesson\n\nold\n\n## 来源\n\n- 文件：lesson.txt (`file-1`)\n")
    drafts = DraftCapture()
    tools = {tool.name: tool for tool in build_chat_tools(notes, None, drafts)}
    token = current_thread_id.set("thread")
    try:
        result = tools["propose_note"].invoke({"action": "append", "file_name": "lesson.md",
                                               "content": "## More\n\nnew"})
    finally:
        current_thread_id.reset(token)
    assert result["status"] == "pending_review"
    assert drafts.draft.action == "replace"
    assert drafts.draft.content.count("## 来源") == 1
    assert drafts.draft.content.index("## More") < drafts.draft.content.index("## 来源")
    assert "file-1" in drafts.draft.content
