from langchain_core.tools import BaseTool
from langchain.tools import tool

from noteagent.chat.drafts import (
    DraftStore,
    NoteDraft,
    current_thread_id,
    markdown_name,
)
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.service import RetrievalService


def build_chat_tools(
    notes: FileNoteRepository,
    retrieval: RetrievalService,
    drafts: DraftStore,
) -> list[BaseTool]:
    """Build list/read/search/propose tools. Disk writes happen only after review."""
    #列处所有文件的工具
    @tool("list_files", description="列出 notes/ 下已有笔记文件名。提案前必须先调用。")
    def list_files() -> dict:
        try:
            return {"files": notes.list_notes()}
        except Exception as exc:
            return {"error": str(exc)}
    #读取文件内容的工具
    @tool(
        "read_file",
        description="读取已存在的笔记。file_name 为文件名如 Agent.md。不能创建或修改文件。",
    )
    def read_file(file_name: str) -> dict:
        if not file_name:
            return {"error": "no target file given"}
        try:
            return {"file_content": notes.read(file_name)}
        except Exception as exc:
            return {"error": str(exc)}
    #从RAG中检索工具
    @tool(
        "search_relative_from_chromadb",
        description="按问题语义检索笔记片段。询问历史知识点时优先使用。",
    )
    def search_relative_from_chromadb(query: str) -> dict:
        try:
            hits = retrieval.search(query, top_k=3)
            docs = [hit.content for hit in hits if hit.content]
            return {"fragments": docs, "count": len(docs)}
        except Exception as exc:
            return {"error": str(exc)}
    #提出笔记建议工具
    @tool(
        "propose_note",
        description=(
            "提交笔记草稿供用户审批，不会写入磁盘。"
            "action 只能是 append（追加到已有文件）或 create（新建文件）。"
            "file_name 如 Backtracking.md。"
            "content 为按用户材料组织的 Markdown：可段落、可 ## / ###；"
            "不是短要点清单。追加时不要写一级标题。"
            "reason 一句话说明分类理由；similar 为逗号分隔的相近已有文件名。"
        ),
    )
    def propose_note(
        action: str,
        file_name: str,
        content: str,
        reason: str = "",
        similar: str = "",
    ) -> dict:
        thread_id = current_thread_id.get()
        if not thread_id:
            return {"error": "no thread_id"}
        if action not in ("append", "create"):
            return {"error": "action must be append or create"}
        if not file_name or not content:
            return {"error": "file_name and content are required"}
        name = markdown_name(file_name)
        exists = notes.exists(name)
        if action == "append" and not exists:
            return {"error": f"{name} does not exist; use create or pick an existing file"}
        if action == "create" and exists:
            return {"error": f"{name} already exists; use append"}
        similar_names = [item.strip() for item in similar.split(",") if item.strip()]
        draft = NoteDraft(
            action=action,
            file_name=name,
            content=content,
            reason=reason,
            similar=similar_names,
            existing_files=notes.list_notes(),
        )
        drafts.put(thread_id, draft)
        return {"status": "pending_review", "action": action, "file_name": name}

    return [list_files, read_file, search_relative_from_chromadb, propose_note]
