# TODO

## Phase 1：Agent 工具层

### 1.1 `write_to_file` 增加覆写模式

**现状**：`write_to_file` 内部 `open(path, "a")` 只能追加，无法修改已有内容。

**方案**：
- 工具签名新增 `mode: str` 参数，取值 `"append"`（默认）或 `"overwrite"`
- `"append"` → `open(path, "a")`，行为不变
- `"overwrite"` → `open(path, "w")`，完全覆写
- 工具描述写清楚两种模式的使用场景——"补充新内容用 append，修正错误用 overwrite"
- 建议在描述中提示 Agent：使用 overwrite 前先 read_from_file 读取当前内容，避免误删

**涉及文件**：`agent/tools.py` 中 `write_to_file` 函数

---

### 1.2 `create_file` 改为按主题命名

**现状**：文件名硬编码为 `YYYY-MM-DD.md`，一天只生成一个文件，不同主题的内容全混在一起。

**方案**：
- 工具签名改为 `create_file(title: str, topic: str = None)`
- `topic` 不为空时，文件名 = `{topic}.md`（如 `Transformer-注意力机制.md`）
- `topic` 为空时，沿用日期命名作为兜底：`{YYYY-MM-DD}.md`
- 文件内容头部自动写入元数据（Front Matter 风格）：
  ```
  ---
  title: {title}
  created: {YYYY-MM-DD HH:MM:SS}
  topic: {topic}
  ---
  
  # {title}
  ```
- 返回值中 `file_path` 保持不变，后续工具通过这个路径操作

**涉及文件**：`agent/tools.py` 中 `create_file` 函数

---

### 1.3 新增 `update_context` 工具

**现状**：系统提示词要求"启动时读 context.md，退出时写总结"，但 `create_file` 只能生成 `YYYY-MM-DD.md`，无法操作 `context.md`，形成设计死锁。

**方案**：
- 新增独立工具，不走 `create_file` 的日期逻辑
- 两个子功能合并为一个工具，通过参数区分：
  - `action="read"` → 读取 `notes/context.md` 并返回内容
  - `action="write"` → 写入/追加内容到 `notes/context.md`
- 追加模式写入，每次总结不超过 500 字符（系统提示词已有约束）
- 如果文件不存在，`read` 返回空字符串 + 提示"尚未有历史记录"；`write` 自动创建

```python
@tool("update_context", description="读写 context.md。action='read' 查看历史学习记录，action='write' 追加本次学习总结（每次≤500字符）")
def update_context(action: str, content: str = "") -> dict:
    context_path = NOTES_DIR / "context.md"
    if action == "read":
        if context_path.exists():
            return {"content": open(context_path, "r", encoding="utf-8").read()}
        return {"content": "", "hint": "尚未有历史记录"}
    if action == "write":
        context_path.parent.mkdir(parents=True, exist_ok=True)
        with open(context_path, "a", encoding="utf-8") as f:
            f.write(content + "\n")
        return {"status": "success"}
    return {"error": "action must be 'read' or 'write'"}
```

**涉及文件**：`agent/tools.py`，`agent/prompts/system_prompts.txt`（同步更新工具名称）

---

### 1.4 清理死代码 + 统一命名

**现状**：
- `screeen_related()` 空函数 + `agent/__init__.py` 导出
- `read__from_file` 工具名双下划线
- `file_name` 参数名与描述中的 `file_path` 不一致
- `config.py` 中 `BASE_URL` 定义但从未使用
- `config.py` 中 `create_model` 的 `model` 参数被忽略
- `router/chat.py` 中 `ResponseModel` 导入但未使用
- 多处 `import os` 未使用

**方案**：
- 删除 `screeen_related()` 整个函数及 `__init__.py` 中的导出
- `read__from_file` → `read_from_file`（去掉双下划线）
- `write_to_file` 和 `read_from_file` 的参数 `file_name` → `file_path`
- `config.py`：删除 `BASE_URL` 行，`create_model` 优先使用传入的 `model` 参数，为空时 fallback 到 `os.getenv("LLM_MODEL", "deepseek-v4-flash")`
- 清理所有未使用的 import

**涉及文件**：`agent/tools.py`, `agent/__init__.py`, `config.py`, `router/chat.py`

---

## Phase 2：记忆系统

### 2.1 代码层强制注入 `context.md`

**现状**：系统提示词"建议"Agent 启动时读 context.md，但没有代码保证执行——Agent 可能直接开始对话，跳过了这个步骤。

**方案**：
- 在 `AgentPipeline.stream_answer()` 中，每次对话开始时：
  1. 读取 `notes/context.md`（如果存在）
  2. 如果内容非空，包装为系统消息插入到 message 列表最前面：
     ```
     [系统] 以下是用户最近的学习记录，请在对话中参考：
     {context.md 内容}
     ```
  3. 如果文件不存在或为空，不注入额外消息
- 不要依赖 Agent 主动调用 `update_context` 工具来读——记忆注入应该是**基础设施级别的行为**，不是 Agent 的自觉

**涉及文件**：`agent/engine.py` 中 `stream_answer()` 方法

---

### 2.2 会话结束触发总结

**现状**：没有"结束会话"的概念，用户离开就是离开了，总结从未生成。

**方案**：
- 前端：侧边栏或顶部加一个"结束并总结"按钮
- 前端点击后：
  1. 发送 `POST /chat/summarize` 请求，body 带 `{thread_id}`
  2. 后端收到后：构造一条固定提示词"请总结本次对话的学习内容，调用 update_context action='write' 写入总结"
  3. Agent 执行总结 → 调用 `update_context` → 写入 `context.md`
  4. 前端收到完成信号后清空聊天区，新会话从干净状态开始
- 总结写入内容由系统提示词约束（`≤500 字符`、`精炼要点`）

**涉及文件**：`router/chat.py`（新增 `/chat/summarize` 路由）、`templates/home.html`（新增按钮+逻辑）

---

### 2.3 笔记自动向量化入库

**现状**：`RAGPipeline.path_to_save()` 只在 `__main__` 示例中调用，Agent 不会自动索引笔记。笔记写了，但搜不到。

**方案**：
- 在 `write_to_file` 工具中，写入成功后自动调用 `rag.path_to_save(file_path)`
- 需要把 `rag` 实例注入到工具的作用域中——当前 `file_related_tools(rag)` 已经传了 rag，直接用
- **防重复**：入库前先按文件名删除 ChromaDB 中已有向量
  - 在 `RAGPipeline` 中新增 `delete_by_file(file_name)` 方法：
    ```python
    def delete_by_file(self, file_name: str):
        """删除指定文件的所有旧向量"""
        self.collection.delete(where={"file_name": file_name})
    ```
  - `path_to_save` 中先调 `delete_by_file`，再 `add`（每个 chunk 的 metadata 里加上 `file_name`）
- **安全**：embedding 调用可能耗时，考虑用 `asyncio.to_thread()` 包装避免阻塞事件循环

**涉及文件**：`agent/tools.py`、`rag/simple_rag.py`

---

### 2.4 `SqliteSaver` 持久化 checkpoint

**现状**：`InMemorySaver()` 在内存中存对话，服务重启后所有历史对话丢失。`thread_id` 也被清空。

**方案**：
- 一行改动：`InMemorySaver()` → `SqliteSaver.from_conn_string("checkpoints.db")`
- 需要 `pip install langgraph-checkpoint-sqlite`（确认 `pyproject.toml` 中已包含依赖或手动添加）
- 在 `AgentPipeline.__init__()` 中初始化：
  ```python
  from langgraph.checkpoint.sqlite import SqliteSaver
  
  self.checkpointer = SqliteSaver.from_conn_string("./checkpoints.db")
  ```
- 前端侧边栏需同步改造——从后端获取所有 thread_id 列表（LangGraph 提供查询 checkpoints 的 API）

**涉及文件**：`agent/engine.py`、`pyproject.toml`

---

## Phase 3：RAG 检索质量

### 3.1 Markdown 结构化分块

**现状**：`RecursiveCharacterTextSplitter` 按字符数暴力切分，`## 标题` 和正文可能被切到不同 chunk，检索时上下文断裂。

**方案**：
- 替换为 `langchain_text_splitters.MarkdownHeaderTextSplitter`
- 按 `##` 一级标题（章节）切分，每个章节作为一个 chunk
- 如果章节过长（>800 字符），再用 `RecursiveCharacterTextSplitter` 二次切分
- 每个 chunk 的 metadata 记录：
  ```python
  {
      "file_name": "Transformer-注意力机制.md",
      "header": "## 多头注意力的计算过程",  # 所属章节标题
      "created_at": "2026-07-30",
      "topic": "Transformer"
  }
  ```
- `RAGPipeline.content_split_to_chunks()` 需要从返回值 `List[str]` 改为 `List[dict]`（包含 text + metadata），或返回两个列表

**涉及文件**：`rag/simple_rag.py` 中 `content_split_to_chunks()` 和 `path_to_save()`

---

### 3.2 向量库增量更新

**现状**：同一文件调两次 `path_to_save` = 两套重复向量。笔记修改后旧向量还活着。

**方案**：
- `path_to_save` 执行流程改为：
  1. `delete_by_file(file_name)` — 按 `file_name` metadata 删旧向量
  2. 重新分块 + embedding
  3. 入库时 metadata 带上 `file_name`、`header`、`created_at`
- ChromaDB 的 `collection.delete(where={"file_name": "xxx.md"})` 按 metadata 过滤删除
- 同时提供一个 `reindex_all()` 方法：遍历 `notes/` 全量重建索引（日常不需要，但迁移/修复时有用）

**涉及文件**：`rag/simple_rag.py`

---

### 3.3 检索加相似度阈值过滤

**现状**：`search_similar` 的 `top_k=3` 固定，即使三条完全不相关也照样返回。

**方案**：
- `search_similar` 新增参数 `distance_threshold: float = 0.6`
- ChromaDB 返回的是距离（越小越相关），相似度 ≈ 1 - distance
- 过滤逻辑：
  ```python
  results = collection.query(query_embeddings=..., n_results=top_k, include=["documents", "distances", "metadatas"])
  filtered = []
  for doc, dist, meta in zip(documents, distances, metadatas):
      if dist < distance_threshold:
          filtered.append({"content": doc, "score": round(1 - dist, 4), "metadata": meta})
  return filtered
  ```
- 如果过滤后为 0 条，直接告诉 Agent "未找到相关结果"，Agent 会诚实告知用户

**涉及文件**：`rag/simple_rag.py` 中 `search_similar()`、`agent/tools.py` 中 `search_relative_from_chromadb`

---

### 3.4 替换中文友好的 Embedding 模型

**现状**：`all-MiniLM-L6-v2` 是英文优化模型（384 维），处理中文笔记时语义匹配精度差。

**方案**：
- 推荐替换为 `BAAI/bge-small-zh-v1.5`（512 维，中文 SOTA 轻量模型，模型大小约 100MB）
- 备选：`shibing624/text2vec-base-chinese`（384 维，与当前维度相同，迁移成本更低）
- 修改位置：
  - `main.py` 中 `embed_model_name` 改为 `"BAAI/bge-small-zh-v1.5"`
  - `rag/simple_rag.py` 中 `init_embed_model` 使用传入的 `model_name`（修掉当前忽略参数直接写死 `all-MiniLM-L6-v2` 的 bug）
  - 去掉 `local_files_only=True`，改为 `local_files_only=False`（首次自动下载），或保留并给出清晰文档说明
- **注意**：换模型后 ChromaDB 旧向量全部失效（维度不同），需要删除 `chromadb_persist/` 并重新索引所有笔记

**涉及文件**：`main.py`, `rag/simple_rag.py`

---

## Phase 4：前端补齐

### 4.1 侧边栏会话列表

**现状**：侧边栏只有"新对话"按钮，写死"对话历史（后续实现）"。

**方案**：
- 后端新增 `GET /api/threads` 路由：查询 LangGraph checkpointer 中所有 thread_id
- 返回格式 `{"threads": [{"thread_id": "xxx", "last_message": "用户的首条消息摘要", "updated_at": "..."}]}`
- 前端：
  - 页面加载时 fetch 线程列表，渲染到侧边栏 `.sidebar-body`
  - 每个线程一行：显示首条消息前 20 字 + 最后活跃时间
  - 点击切换 → 更新 `currentThreadId`，加载对应历史对话（`GET /api/threads/{thread_id}/messages`）
  - 当前线程高亮

**涉及文件**：`router/chat.py`（新增路由）、`templates/home.html`

---

### 4.2 笔记文件面板

**现状**：笔记只存文件系统，前端没有任何入口可以查看/浏览。

**方案**：
- 后端新增 `GET /api/notes` 路由：扫描 `notes/` 目录，返回所有 `.md` 文件列表 + 元数据（文件名、大小、创建时间、Front Matter 中的 title/topic）
- 后端新增 `GET /api/notes/{file_name}`：返回文件的 Markdown 原始内容
- 前端：
  - 侧边栏下半部分或独立 Tab 切换"笔记"面板
  - 文件列表点击后，在右侧聊天区以只读 Markdown 渲染展示（复用已有的 `marked.js`）
  - 展示完后可以点击返回继续对话

**涉及文件**：`router/chat.py`（或新建 `router/notes.py`）、`templates/home.html`

---

### 4.3 笔记搜索框

**现状**：只能在对话里通过 Agent 调用检索工具，没有独立的搜索入口。

**方案**：
- 后端已有 `search_relative_from_chromadb` 工具逻辑，可直接在路由里调用 `RAG.search_similar()`
- 新增 `POST /api/search` 路由：接收 `{query}`，返回匹配片段列表 + 来源文件
- 前端：
  - 侧边栏顶部加一个搜索框
  - 输入关键词 → 后端检索 → 结果列表展示（每个结果：片段内容 + 相似度分数 + 来源文件名）
  - 点击某个结果 → 跳转到笔记文件预览（复用 4.2 的文件预览）

**涉及文件**：`router/chat.py`、`templates/home.html`

---

## Phase 5：后续（按需引入）

### 5.1 SQLite 笔记元数据表

**触发条件**：笔记超过 50 个，按主题/标签筛选成为刚需时再引入。

**方案**：
- 新建 `core/metadata.py`，定义 SQLite 表结构：
  ```sql
  CREATE TABLE notes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      file_name TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      topic TEXT,
      tags TEXT,           -- JSON array: ["NLP", "Transformer"]
      word_count INTEGER,
      created_at TEXT,
      updated_at TEXT
  );
  ```
- `create_file` 时写入一条记录，`write_to_file` 时更新 `updated_at`
- 前端笔记面板支持按 topic/tag 筛选、按时间排序

### 5.2 笔记质量反馈回路

**触发条件**：用户在知识问答中频繁修正/"这个笔记不对"时引入。

**方案**：
- 检索结果展示时附带 👍/👎 按钮
- 点赞 → metadata 中增加 `score += 1`，提升检索权重
- 点踩 → 降权，同时触发 Agent 询问"需要修正这条笔记吗？"

### 5.3 屏幕内容捕获 + OCR

**触发条件**：核心闭环跑通并打磨稳定后再考虑。

**方向**：
- B 站字幕抓取（`bilibili-api`）作为最低成本入口
- 音频 → Whisper ASR 本地语音识别
- 截图 + 多模态模型理解（预留 `screeen_related` 原来那个坑位）
