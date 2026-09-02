# NoteAgent 检索（RAG）

全局职责见 [architecture.md §5.2.7](./architecture.md#527-检索)。本文是现行切块、向量点、审批后同步与查询路径。聊天工具只读入口见 [chat-tools.md §4.3](./chat-tools.md#43-search_relative_from_chromadb)。

| 项 | 内容 |
|---|---|
| 事实源 | 人审后的 `notes/*.md`。Chroma 是派生索引，可删光按文件重建 |
| 触发 | `commit_review` 写盘成功后同步该 `file_name`；`reject` 不碰向量 |
| 切块 / 模型 | `MarkdownChunker` 500/50；默认 `all-MiniLM-L6-v2`。换模型只改环境变量 |
| 不是 | 用户勾选入库、PDF 直接 embed、出处 SSE、标题感知切块 |

`retrieval` 不改笔记文件、不写 PostgreSQL、不调聊天模型。`notes` / `retrieval` 不得 import `chat`。

---

## 1. 要解决什么

已批准笔记要能被下一句语义问到，且改写、删文件后不能搜到过期段落。

向量库不裁决「两篇笔记冲不冲突」。文件名冲突和内容对错在提案与人审里解决。Chroma 只镜像**某一篇当前磁盘正文**的切块。

未审批草稿、聊天气泡、模型回复不进向量库。

---

## 2. 谁进库

| 来源 | 进 Chroma？ |
|------|-------------|
| 人审写入或改过的 `notes/*.md` | 是。按文件整篇重建 |
| 人审删除的文件 | 否。只删该 `file_name` 的点 |
| `DraftStore`、PG 消息、`context.md` | 否 |
| 用户 PDF / 图片 / 网页正文 | 否（现行无此路径） |

进程启动**不会**扫描 `notes/` 全量索引。盘上已有、从未经过这次同步的文件，要搜到仍须对该篇跑 [`scripts/index_notes.py`](../../scripts/index_notes.py)，或再批准一次写盘。

---

## 3. 写入路径

```text
POST /chat/review
  → commit_review 改磁盘
  → _sync_index
       delete     → RetrievalService.delete_note(file_name)
       create / append / replace → index_note(file_name)
```

`index_note`：

1. `delete_note`：`where file_name = 该文件` 删点。从未索引过则无操作。
2. `notes.read` 当前全文（append 也是整篇，不是只切新段落）。
3. `MarkdownChunker.split`。
4. 空则停止（旧点已删）。
5. `embed_documents` → id `{file_name}_{i}` → `upsert`。

`ChatAgent.review` 把容器里的 `RetrievalService` 传入 `commit_review`。单测可不传 `retrieval`，此时只写盘。

索引抛错：`_sync_index` 记 exception，**不回滚** Markdown，HTTP 仍 `{status: written, ...}`。人审与向量不是同一事务。

手动脚本走同一条 `index_note`（同样先删再写），给 collection 损坏或历史文件补索引用。

---

## 4. 一个向量点里有什么

Chroma collection 名来自 `CHROMA_COLLECTION`（默认 `my_knowledge`），目录 `CHROMA_DIR`。

| 字段 | 现行值 |
|------|--------|
| id | `{file_name}_{chunk_index}`，如 `Go.md_0` |
| embedding | 该切块的句向量 |
| document | 切块原文，查询时作为 `SearchHit.content` |
| metadata.file_name | 笔记文件名，删除与重建的键 |
| metadata.chunk_index | 本篇内从 0 起的序号 |

没有：章节路径、创建时间、`note_id`、来源 URL、内容哈希。笔记身份就是扁平目录下的 `file_name`。列表若要「最近改过」用文件系统 mtime，不写进点 metadata。

---

## 5. 切块与向量化

[`MarkdownChunker`](../../src/noteagent/retrieval/chunker.py)：`RecursiveCharacterTextSplitter`，`chunk_size=500`，`chunk_overlap=50`，`length_function=len`。分隔符优先段落、换行、中文句读。不解析 `##` / `###`，一块可以跨节，也可以从一节中间切开。

[`SentenceTransformerEmbedder`](../../src/noteagent/retrieval/embedder.py)：本地 `SentenceTransformer`，`cache_folder` 为 `EMBEDDING_CACHE_DIR`。`embed_documents` 与 `embed_query` 必须是同一模型。默认 `all-MiniLM-L6-v2`。`EMBEDDING_LOCAL_FILES_ONLY=true` 时不联网下载。

换 embedding 模型后，新旧向量不能混用，需要按篇 `index_note` 重建（或删掉 persist 目录再编）。

测试用假 embedder，不加载真实句向量模型。黄金集（尚未填）在 [`evals/rag/`](../../evals/rag/README.md)，不进 pytest。

---

## 6. 查询路径

问旧知识时，模型调 `search_relative_from_chromadb(query)`：

1. `RetrievalService.search(query, top_k=3)`（**3 写死在工具里**）。
2. 问句 `embed_query`，Chroma 近邻，`include` documents / distances / metadatas。
3. 每条变成 `SearchHit(content, distance, metadata)`。
4. 工具**只**把非空 `content` 放进 `{fragments, count}`，丢掉 `file_name` 与 `distance`。
5. 全文进当前 Turn 的 Runtime `ToolMessage`；前端气泡看不到工具结果。

空库或未索引时 `fragments` 可以为 `[]`，不是工具错误。无相似度阈值：再差的 3 条也会交给模型。无 `insufficient_evidence`。前端无 sources 事件。

---

## 7. 失败与重建

| 情况 | 行为 |
|------|------|
| 写盘失败 | 不索引；draft 放回 store |
| 写盘成功、embed / Chroma 失败 | 文件保留；日志 `draft index failed` |
| 向量库目录损坏 | 删 persist 或对每篇跑 `index_notes.py` |
| 缩短 replace 仍只 upsert、不先删 | **现行已先删。** 旧实现会残留高序号 id |

索引步骤由 [`IndexTrace`](../../src/noteagent/observability/index_trace.py) 写入 `var/logs/noteagent.log`（logger `noteagent.observability.index_trace`），INFO 不打切块原文。`RetrievalService` 只做删点/切块/embed/入库，并在步骤边界调用 tracer。一次 `index_note` 顺序为：`index start` → `index delete file= elapsed_ms=` →（仓库）`note read` → `index chunked file= chunks= chars=` → `index embedded … elapsed_ms=` → `index upserted … elapsed_ms=` → `index done … elapsed_ms=`。空切块在 read 之后 `index skip empty`，无 chunked/embedded/upserted。人审侧另有 `draft indexed` / `draft index failed`。查询仍是 `search query= hits=`。

---

## 8. 本文件不覆盖

下列不是现行代码，不要按已上线实现：

- 按 H2/H3 切块、中文 embedding、命中阈值、每篇 chunk 上限
- SSE / 气泡下的出处芯片（`file_name` 已在点上，工具未传出）
- 笔记 YAML、`notes` 元数据表、创建时间进向量
- PDF / OCR / URL 入库、勾选哪些文件进库
- 混合检索、rerank、独立 Retrieval HTTP

实现切片：[docs/plans/2026-09-02-auto-index-on-approve.md](../plans/2026-09-02-auto-index-on-approve.md)。更长的入库 Job 设想见 [docs/plans/draft-generation.md](../plans/draft-generation.md)，不是本文。

---

## 9. 代码落点

| 路径 | 职责 |
|------|------|
| [`src/noteagent/retrieval/chunker.py`](../../src/noteagent/retrieval/chunker.py) | 字符切块 |
| [`src/noteagent/retrieval/embedder.py`](../../src/noteagent/retrieval/embedder.py) | 本地句向量 |
| [`src/noteagent/retrieval/vector_store.py`](../../src/noteagent/retrieval/vector_store.py) | upsert / query / `delete_by_file_name` |
| [`src/noteagent/retrieval/service.py`](../../src/noteagent/retrieval/service.py) | `index_note`、`delete_note`、`search` |
| [`src/noteagent/observability/index_trace.py`](../../src/noteagent/observability/index_trace.py) | 索引/检索步骤 INFO |
| [`src/noteagent/retrieval/models.py`](../../src/noteagent/retrieval/models.py) | `SearchHit` |
| [`src/noteagent/chat/drafts.py`](../../src/noteagent/chat/drafts.py) | `_sync_index` |
| [`src/noteagent/chat/agent.py`](../../src/noteagent/chat/agent.py) | `review` 注入 `retrieval` |
| [`src/noteagent/bootstrap/app.py`](../../src/noteagent/bootstrap/app.py) | 装配 `RetrievalService` |
| [`scripts/index_notes.py`](../../scripts/index_notes.py) | 按篇重建 |
| [`src/noteagent/bootstrap/settings.py`](../../src/noteagent/bootstrap/settings.py) | `CHROMA_*`、`EMBEDDING_*` |

包说明（与代码同步的目录表）：[`src/noteagent/retrieval/README.md`](../../src/noteagent/retrieval/README.md)。
