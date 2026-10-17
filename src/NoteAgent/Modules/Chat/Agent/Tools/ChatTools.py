from langchain_core.tools import BaseTool
from langchain.tools import tool

from NoteAgent.Modules.Chat.Agent.Citations.CitationRegistry import current_citations
from NoteAgent.Modules.Chat.Agent.Tools.NoteSources import (
    current_source_evidence,
    merge_source_section,
    render_source_section,
    select_sources,
    source_urls_in_section,
    strip_source_section,
)
from NoteAgent.Modules.Chat.Agent.Tools.WebReading import WebPageReader
from NoteAgent.Modules.Conversations.Service.PendingDrafts import WRITE_ACTIONS, DraftStore, NoteDraft, ProposeNoteInput, current_thread_id, markdown_name
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from NoteAgent.Modules.Retrieval.Service.NoteRetrievalService import RetrievalService
from NoteAgent.Modules.Sources.Service.SourceFileAccess import authorized_source_ids, read_source_ids
from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService, SourceFileError
from NoteAgent.Modules.Chat.Agent.Tools.NoteSources import SOURCE_SECTION_TITLE


def build_chat_tools(
    notes: FileNoteRepository,
    retrieval: RetrievalService | None,
    drafts: DraftStore,
    repairs=None,
    web_reader: WebPageReader | None = None,
    source_files: SourceFileService | None = None,
) -> list[BaseTool]:
    """Build list/read/search/propose tools. Disk writes happen only after review.

    ``retrieval`` may be None while the embedding index is unavailable (for example after
    a model switch that has not been rebuilt yet); the search tool then reports that
    instead of returning an empty result that would read as "no matching note".

    ``web_reader`` is optional: without it the reader tool is not registered at all, so a
    test container can never make an unexpected network request.
    """
    #列处所有文件的工具
    @tool("list_files", description="列出 notes/ 下已有笔记相对路径（含 Folder/Note.md）和一层文件夹名。提案前必须先调用。")
    def list_files() -> dict:
        try:
            return {"files": notes.list_notes(), "folders": notes.list_folders()}
        except Exception as exc:
            return {"error": str(exc)}
    #读取文件内容的工具
    @tool(
        "read_file",
        description="读取已存在的笔记。file_name 为相对路径，如 Agent.md 或 Python/GIL.md。不能创建或修改文件。",
    )
    def read_file(file_name: str) -> dict:
        if not file_name:
            return {"error": "no target file given"}
        try:
            name = notes.normalize(file_name)
            content = notes.read(name)
        except Exception as exc:
            return {"error": str(exc)}
        payload: dict = {"file_content": content}
        registry = current_citations.get()
        if registry is not None:
            payload["source_id"] = registry.register(file_name=name)
        return payload
    #从RAG中检索工具
    @tool(
        "search_relative_from_chromadb",
        description=(
            "按问题语义检索笔记片段。询问历史知识点时优先使用。"
            "每条片段带 file_name、heading_path 与 start_char/end_char，可直接据此定位原文。"
        ),
    )
    def search_relative_from_chromadb(query: str) -> dict:
        if retrieval is None:
            return {"error": "检索索引当前不可用（向量模型需要重建），请改用 read_file 读取指定笔记"}
        try:
            hits = repairs.search_synced(retrieval, query, top_k=3) if repairs else retrieval.search(query, top_k=3)
        except Exception as exc:
            return {"error": str(exc)}
        registry = current_citations.get()
        fragments: list[dict] = []
        for hit in hits:
            if not hit.content:
                continue
            metadata = hit.metadata or {}
            file_name = str(metadata.get("file_name") or "")
            # 片段自带定位信息：模型不该靠解析 source_id 猜文件名或章节。
            item: dict = {"content": hit.content}
            if file_name:
                item["file_name"] = file_name
            heading_path = str(metadata.get("heading_path") or "")
            if heading_path:
                item["heading_path"] = heading_path
            start_char = metadata.get("start_char")
            end_char = metadata.get("end_char")
            if isinstance(start_char, int) and isinstance(end_char, int):
                item["start_char"] = start_char
                item["end_char"] = end_char
            if registry is not None and file_name:
                raw_index = metadata.get("chunk_index")
                chunk_index = int(raw_index) if raw_index is not None else None
                item["source_id"] = registry.register(
                    file_name=file_name,
                    chunk_index=chunk_index,
                    quote=hit.content,
                )
            fragments.append(item)
        return {"fragments": fragments, "count": len(fragments)}
    #提出笔记建议工具
    @tool(
        "propose_note",
        description=(
            "When a source file was read and used in the note body, include its ID in source_file_ids. "
            "提交笔记草稿供用户审批，不会写入磁盘。"
            "action：append 追加；create 新建；replace 覆盖已有全文；delete 删除文件。"
            "新内容默认 append 或 create。更正过时正文才 replace；明确删文件才 delete。"
            "file_name 如 Backtracking.md 或 Python/GIL.md。"
            "content 为 Markdown。create/append 不要写一级标题；"
            "replace 须为读到的完整文件（含原有一级标题）；delete 可空。"
            "reason 一句话说明分类理由；similar 为逗号分隔的相近已有文件名。"
        ),
        args_schema=ProposeNoteInput,
    )
    def propose_note(
        action: str,
        file_name: str,
        content: str,
        reason: str = "",
        similar: str = "",
        source_urls: list[str] | None = None,
        user_supplied_source_urls: list[str] | None = None,
        source_file_ids: list[str] | None = None,
    ) -> dict:
        thread_id = current_thread_id.get()
        if not thread_id:
            return {"error": "no thread_id"}
        if action not in WRITE_ACTIONS:
            return {"error": "action must be append, create, replace, or delete"}
        if not file_name:
            return {"error": "file_name is required"}
        if action != "delete" and not content:
            return {"error": "content is required"}
        name = markdown_name(file_name)
        exists = notes.exists(name)
        if action in ("append", "replace", "delete") and not exists:
            return {"error": f"{name} does not exist; use create or pick an existing file"}
        if action == "create" and exists:
            return {"error": f"{name} already exists; use append"}
        similar_names = [item.strip() for item in similar.split(",") if item.strip()]
        evidence = current_source_evidence.get()
        if (action != "delete" and evidence is not None
                and (evidence.fetched_ok or evidence.user_provided_after_failure)
                and source_urls is None and user_supplied_source_urls is None):
            return {"error": "网页笔记必须明确传入 source_urls 和 user_supplied_source_urls；未采用网页时传空列表"}
        # Only sources this session can prove reach the note; the section is rendered here
        # so the approval preview and the written file already contain the final block.
        sources, provided = select_sources(
            source_urls or [], user_supplied_source_urls or [], evidence
        )
        selected_files = list(dict.fromkeys(source_file_ids or []))
        if any(file_id not in (read_source_ids.get() or set()) for file_id in selected_files):
            return {"error": "来源文件必须先由本会话工具实际读取"}
        file_lines = []
        if source_files is not None:
            for file_id in selected_files:
                try:
                    source = source_files.get(file_id)
                    if source.status != "ready":
                        return {"error": "来源文件已不可用"}
                    file_lines.append(f"- 文件：{source.display_name} (`{file_id}`)")
                except (SourceFileError, ValueError):
                    return {"error": "来源文件已不可用"}
        if action in ("append", "replace"):
            old = notes.read(name)
            old_sources, old_provided = source_urls_in_section(old)
            old_file_lines = [line for line in old.split(SOURCE_SECTION_TITLE, 1)[-1].splitlines()
                              if line.startswith("- 文件：")] if SOURCE_SECTION_TITLE in old else []
            if old_sources or old_provided or old_file_lines:
                # An append after a source section would place old sources in the
                # middle. Show the complete merged file and write it as replace.
                if action == "append":
                    content = old.rstrip() if not content.strip() else (
                        strip_source_section(old).rstrip() + "\n\n" +
                        strip_source_section(content).lstrip()
                    )
                    action = "replace"
                if strip_source_section(old).strip() in strip_source_section(content):
                    sources = list(dict.fromkeys([*old_sources, *sources]))
                    provided = list(dict.fromkeys([*old_provided, *provided]))
                    file_lines = list(dict.fromkeys([*old_file_lines, *file_lines]))
        if action != "delete" and (sources or provided or file_lines or SOURCE_SECTION_TITLE in content):
            section = render_source_section(sources, provided)
            if file_lines:
                section = (section.rstrip() + "\n" if section else SOURCE_SECTION_TITLE + "\n\n") + "\n".join(file_lines) + "\n"
            content = merge_source_section(content, section)
        draft = NoteDraft(
            action=action,
            file_name=name,
            content=content,
            reason=reason,
            similar=similar_names,
            existing_files=notes.list_notes(),
            source_urls=sources,
            user_supplied_source_urls=provided,
            source_file_ids=selected_files,
        )
        drafts.put(thread_id, draft)
        return {"status": "pending_review", "action": action, "file_name": name}

    tools: list[BaseTool] = [list_files, read_file, search_relative_from_chromadb, propose_note]

    if source_files is not None:
        @tool("list_source_files", description="列出本会话用户已发送的来源附件 ID、名称和状态。")
        def list_source_files() -> dict:
            result = []
            for source_id in sorted(authorized_source_ids.get()):
                try:
                    source = source_files.get(source_id)
                    result.append({"id": source_id, "name": source.display_name, "status": source.status})
                except (SourceFileError, ValueError):
                    result.append({"id": source_id, "status": "unavailable"})
            return {"files": result}

        @tool("read_source_file", description="按本会话附件 ID 读取解析内容；可选 locator 精确定位页或段落。单次最多返回 12000 字符。")
        def read_source_file(source_id: str, locator: str = "") -> dict:
            if source_id not in authorized_source_ids.get():
                return {"error": "来源文件不属于当前会话"}
            try:
                source = source_files.get(source_id)
                parts = source_files.read_fragments(source_id)
            except (SourceFileError, ValueError):
                return {"error": "来源文件已不可用或尚未解析完成"}
            matching = [p for p in parts if not locator or p.locator == locator]
            if not matching:
                return {"error": "未找到指定定位"}
            rendered = "\n\n".join(f"[{p.locator}] {p.text}" for p in matching)
            used = read_source_ids.get()
            if used is not None:
                used.add(source_id)
            return {"id": source_id, "name": source.display_name,
                    "content": rendered[:12000], "truncated": len(rendered) > 12000}

        tools.extend([list_source_files, read_source_file])

    if web_reader is not None:
        @tool(
            "read_webpage",
            description=(
                "读取用户给出的一个网页 URL，返回页面标题与抽取后的正文。"
                "用户本句里出现的每个 URL 都要逐个调用本工具；不要自行搜索或替换来源。"
                "status：ok 表示完整读取；partial 表示正文过长或响应过大被截断；"
                "login_required/blocked/unsupported/failed 表示未读取成功，此时 content 为空、error 为简短原因。"
                "未成功读取的 URL 不得当作已读内容使用。"
            ),
        )
        async def read_webpage(url: str) -> dict:
            result = await web_reader.read(url)
            return {
                "url": result.url,
                "final_url": result.final_url,
                "status": result.status,
                "title": result.title,
                "content": result.content,
                "error": result.error,
            }

        tools.append(read_webpage)

    return tools
