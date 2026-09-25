# NoteAgent 检索（RAG）

全局职责见 [architecture.md §5.6](./architecture.md#56-检索)。本文是现行切块、向量点、审批后同步与查询路径。聊天工具只读入口见 [chat-tools.md §4.3](./chat-tools.md#43-search_relative_from_chromadb)。

| 项 | 内容 |
|---|---|
| 事实源 | 人审后的 `notes/*.md`。Chroma 是派生索引，可删光按文件重建 |
| 触发 | 聊天 `commit_review` 写盘成功后同步该 `file_name`；Documents `/notes*` 写盘或点芯片同样走 `index_note` / `delete_note`；`reject` 不碰向量 |
| 切块 / 模型 | `MarkdownChunker` 500/50、策略 `heading`、`embed_heading_prefix=True`（由 [rag-v1-report.md](../evaluations/rag-v1-report.md) 的任务六对照选出，可用 `CHUNK_STRATEGY` / `EMBED_HEADING_PREFIX` 覆盖）；默认 `intfloat/multilingual-e5-small`（由评测选出，可用 `EMBEDDING_MODEL` 覆盖），按其官方要求自动加 `query:` / `passage:` 前缀。换模型、换切块策略或换编码指令都必须重建 |
| 配置一致性 | collection metadata 存配置指纹 `策略\|模型\|被嵌入文本`；与当前配置不符时构造 `RetrievalService` 即报错要求重建 |
| 运行期选择 | 界面可切换本地向量模型。启动时以持久化的 active 为准（优先于 `EMBEDDING_MODEL`），切换走 §7.1 的维护窗口 |
| 不是 | 用户勾选入库、PDF 直接 embed、命中阈值 |

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
| Documents 新建 / 保存 / 移动 / 点「未索引」 | 是。同一条 `index_note` |
| 人审或 Documents 删除的文件 | 否。只删该 `file_name` 的点 |
| `DraftStore`、PG 消息、`context.md` | 否 |
| 用户 PDF / 图片 / 网页正文 | 否（现行无此路径） |

进程启动**不会**扫描 `notes/` 全量索引。盘上已有、从未经过这次同步的文件，要搜到仍须对该篇跑 [`scripts/index_notes.py`](../../scripts/index_notes.py)，或在 Documents 点「未索引」，或再批准一次写盘。

---

## 3. 写入路径

```text
POST /chat/review
  → commit_review 改磁盘
  → _sync_index
       delete     → RetrievalService.delete_note(file_name)
       create / append / replace → index_note(file_name)

PUT / POST / DELETE /notes* 、POST /notes/{path}/index
  → notes/router 改磁盘（index 接口不改文件）
  → _try_index / _try_delete_index（同一套 index_note / delete_note）
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

界面切换向量模型时，重建写入的是**该模型专属的 collection**：`{CHROMA_COLLECTION}__{模型短名}`（如 `my_knowledge__multilingual-e5-small`）。不同模型的向量不可比，所以切换不会写进旧模型建的集合；模型加载失败或构建失败时旧集合原样保留，也不会有任何旧集合被自动删除。切换回原模型时按 `{CHROMA_COLLECTION}` 之外的专属名重建一次全量索引，因此不会拿过期集合冒充新索引。

| 字段 | 现行值 |
|------|--------|
| id | `{file_name}_{chunk_index}`，如 `Go.md_0` |
| embedding | 该切块的句向量（嵌入文本见 §5） |
| document | 切块原文，**必须是笔记正文的连续切片**；查询时作为 `SearchHit.content`，引用与位置校验都靠它 |
| metadata.file_name | 笔记文件名，删除与重建的键 |
| metadata.chunk_index | 本篇内从 0 起的序号 |
| metadata.heading_path | 该块所属章节路径，如 `回溯算法 > 回溯法理论基础 > 什么是回溯法`；不在任何标题下时为空串 |
| metadata.start_char / end_char | 该块在笔记**解码后文本**中的字符区间（左闭右开）；语料为 CRLF 文件，但应用读到的是 `read_text` 规范化后的 LF 文本，偏移以它为准 |
| metadata.content_sha256 | 切块内容的哈希，用于发现索引与磁盘正文漂移 |

collection 自身的 metadata 另存配置指纹（见上表「配置一致性」）。

短笔记只切出一块时，collection 里就是一条（embedding 为默认模型的 384 维，此处省略）：

```json
{
  "id": "Go.md_0",
  "embedding": [0.012, "..."],
  "document": "注意力机制用 Query Key Value 计算权重。\n",
  "metadata": {
    "file_name": "Go.md",
    "chunk_index": 0,
    "heading_path": "Go 语言 > 并发模型",
    "start_char": 0,
    "end_char": 21,
    "content_sha256": "..."
  }
}
```

子目录笔记的 `id` 与 `file_name` 带相对路径，如 `Lang/Go.md_0`。

没有：创建时间、来源 URL。笔记身份就是扁平目录下的 `file_name`。列表若要「最近改过」用文件系统 mtime，不写进点 metadata。

---

## 5. 切块与向量化

[`MarkdownChunker`](../../src/noteagent/retrieval/chunker.py)：`RecursiveCharacterTextSplitter`，`chunk_size=500`，`chunk_overlap=50`，`length_function=len`。分隔符优先段落、换行、中文句读。

两种策略，`split()` 保持返回字符串列表的兼容入口，索引走 `split_with_metadata()`：

- `char`：只按长度递归切分，一块**可以跨节**，也可以从一节中间切开。评测里的旧基线，可复现。
- `heading`（现行生产配置）：先按标题切段；短章节整块保留（标题不会与正文分离），长章节继续按长度切分。标题解析是**围栏感知**的——语料里有一篇的代码注释形如 `# xxx`，纯文本扫描会把它当成标题。

每个块都带 `heading_path` 与 `start_char`/`end_char`，偏移由切分器给出并在写入前用切片校验（`text[start:end] == content`），不靠事后字符串搜索猜位置。

[`SentenceTransformerEmbedder`](../../src/noteagent/retrieval/embedder.py)：本地 `SentenceTransformer`，`cache_folder` 为 `EMBEDDING_CACHE_DIR`。`embed_documents` 与 `embed_query` 必须是同一模型。默认 `intfloat/multilingual-e5-small`，编码指令见 [`MODEL_INSTRUCTIONS`](../../src/noteagent/retrieval/embedder.py)。`EMBEDDING_LOCAL_FILES_ONLY=true` 时不联网下载。

**被嵌入的文本可以不是引用原文。** `embed_heading_prefix=True` 时嵌入文本为 `heading_path + 换行 + 正文`，而 Chroma 的 `document` 始终存正文切片，保证引用可映射回原文。

**注意输入上限。** 各模型的 `max_seq_length` 差异很大（MiniLM-L6 只有 256 token，e5-small/bge-zh 是 512），超出的部分被模型静默截断；选型时这是第一条判据。评测 run 会把每块的实际 token 数与被截断块数写进报告（`token_budget`）；字符数不是可靠代理。

换 embedding 模型或换切块策略后，新旧向量不能混用，需要按篇 `index_note` 重建（或删掉 persist 目录再编）。配置指纹不一致时 `RetrievalService` 会直接拒绝启动，见上表。

测试用假 embedder，不加载真实句向量模型。检索评测数据在 [`evals/rag/`](../../evals/rag/README.md)，不进 pytest 默认套件里的联网部分。

---

## 6. 查询路径

问旧知识时，模型调 `search_relative_from_chromadb(query)`：

1. `RetrievalService.search(query, top_k=3)`（**3 写死在工具里**）。
2. 问句 `embed_query`，Chroma 近邻，`include` documents / distances / metadatas。
3. 每条变成 `SearchHit(content, distance, metadata)`。
4. 工具把非空 `content` 交给模型，并带本轮 `source_id`；`file_name` 只进服务端 `CitationRegistry`，不放进工具返回。
5. 全文进当前 Turn 的 Runtime `ToolMessage`；前端气泡看不到工具结果。模型句末 `[[cite:N]]` 由聊天层映射成 ①。

空库或未索引时 `fragments` 可以为 `[]`，不是工具错误。无相似度阈值：再差的 3 条也会交给模型。无 `insufficient_evidence`。聊天 SSE 有 `sources`（本条助手消息实际引用，编号 1..n），见 [frontend.md](./frontend.md)。

---

## 7. 失败与重建

| 情况 | 行为 |
|------|------|
| 写盘失败 | 不索引；draft 放回 store |
| 写盘成功、embed / Chroma 失败 | 文件保留；日志 `draft index failed` |
| 向量库目录损坏 | 删 persist 或对每篇跑 `index_notes.py` |
| 缩短 replace 仍只 upsert、不先删 | **现行已先删。** 旧实现会残留高序号 id |
| 配置指纹与 collection 不符 | 构造 `RetrievalService` 抛 `IndexConfigMismatch`，附两边指纹与「重建」提示；不静默用旧向量 |
| 加指纹之前建的旧索引 | 视作 legacy 默认配置（`char:500/50\|all-MiniLM-L6-v2\|content`）；配置未变则照常可用，变了才要求重建 |
| 切块器产出的块不是正文连续切片 | 抛 `ValueError` 并记日志；不写入无法定位的偏移 |

索引步骤 logger 与一次 `index_note` 的日志顺序见 [observability.md](./observability.md) §4。INFO 不打切块原文。`RetrievalService` 只做删点/切块/embed/入库，并在步骤边界调用 `IndexTrace`。人审侧另有 `draft indexed` / `draft index failed`。

### 7.1 界面切换向量模型（维护窗口）

单进程串行维护，不做双写或增量追赶。`ModelRuntimeService`（[`model_management/service.py`](../../src/noteagent/model_management/service.py)）持有唯一的 `RuntimeSnapshot`（chat agent + retrieval + embedding 状态 + revision），请求通过 `read` / `write` / `chat` 取一次快照并在整个操作内使用：

1. 门禁锁内确认没有正在进行的聊天/写操作，再开维护窗口（检查与设置必须原子）。已有请求继续持有旧快照到 `finally` 释放。
2. 后台线程用 `local_files_only=true` 加载目标模型，按 `{collection}__{模型短名}` 建全新 collection。
3. 逐篇 `index_note` 并汇报进度；目标集合里磁盘上已不存在的 `file_name` 会删掉（`indexed_files()`，避免残留幽灵片段）。`scripts/index_notes.py` 与界面共用 `index_targets()`，README.md 与 `bak/` 的排除规则一致。
4. 构建前后比对笔记清单与内容 hash；不一致（外部改过文件）则任务失败，旧索引保留。非空语料必须切出至少一块，并至少用真实语料搜到一次命中；空语料允许成功建空索引。
5. 原子写 `active_embedding` 与 revision，然后用**一次替换**发布新的检索对象与绑定它的 Agent/工具。任一步失败都保留旧对象，job 记为 `failed`。
6. 维护期间 `/chat`、审批的 approve/override、所有 `/notes` 写接口返回 409（`code=busy`），拒绝发生在建会话/写消息/落盘之前；reject 草稿走只读租约因此仍可用；读笔记、读历史、`GET /model-settings` 不受影响。
7. 重启时读最后一次成功的 active；`running` 的 job 记为 `interrupted`，绝不自动启用半成品。lifespan 退出时停止接受新任务，并阻止进行中的任务发布。

维护窗口内不要同时跑索引 CLI：外部进程不受内存门禁约束，会让步骤 4 的 hash 比对失败。本期单进程单 worker。

---

## 8. 本文件不覆盖

下列不是现行代码，不要按已上线实现：

- 命中阈值、每篇 chunk 上限、混合检索、rerank
- 中文 embedding 模型（已评测选型，见 [rag-v1-report.md](../evaluations/rag-v1-report.md)）
- 气泡下额外出处芯片、NLI 引用校验
- 笔记 YAML、`notes` 元数据表、创建时间进向量
- PDF / OCR / URL 入库、勾选哪些文件进库
- 独立 Retrieval HTTP

按 H2/H3 切块是现行配置（`strategy="heading"`）；工具是否返回 `heading_path` 属于 [chat-tools.md](./chat-tools.md) 的范围，当前**未返回**。

实现切片：[docs/plans/2026-09-02-auto-index-on-approve.md](../plans/2026-09-02-auto-index-on-approve.md)、[docs/plans/2026-09-25-rag-quality-improvement.md](../plans/2026-09-25-rag-quality-improvement.md)（任务六）。更长的入库 Job 设想见 [docs/plans/draft-generation.md](../plans/draft-generation.md)，不是本文。

---

## 9. 代码落点

| 路径 | 职责 |
|------|------|
| [`src/noteagent/retrieval/chunker.py`](../../src/noteagent/retrieval/chunker.py) | 字符 / 章节切块，输出块与偏移 |
| [`src/noteagent/retrieval/markdown.py`](../../src/noteagent/retrieval/markdown.py) | 围栏感知的标题解析与 `heading_path`（检索与评测共用） |
| [`src/noteagent/retrieval/embedder.py`](../../src/noteagent/retrieval/embedder.py) | 本地句向量 |
| [`src/noteagent/retrieval/vector_store.py`](../../src/noteagent/retrieval/vector_store.py) | upsert / query / `delete_by_file_name` |
| [`src/noteagent/retrieval/service.py`](../../src/noteagent/retrieval/service.py) | `index_note`、`delete_note`、`search`、`indexed_files`、`index_targets` |
| [`src/noteagent/observability/index_trace.py`](../../src/noteagent/observability/index_trace.py) | 索引/检索步骤 INFO |
| [`src/noteagent/retrieval/models.py`](../../src/noteagent/retrieval/models.py) | `SearchHit`、`NoteChunk` |
| [`src/noteagent/chat/drafts.py`](../../src/noteagent/chat/drafts.py) | `_sync_index` |
| [`src/noteagent/chat/agent.py`](../../src/noteagent/chat/agent.py) | `review` 注入 `retrieval` |
| [`src/noteagent/bootstrap/runtime.py`](../../src/noteagent/bootstrap/runtime.py) | 唯一的 Agent/工具/检索装配入口（`BootstrapAssembler`） |
| [`src/noteagent/bootstrap/app.py`](../../src/noteagent/bootstrap/app.py) | 装配 `ModelRuntimeService` 并注册路由 |
| [`src/noteagent/model_management/service.py`](../../src/noteagent/model_management/service.py) | 运行快照、门禁、向量重建任务 |
| [`scripts/index_notes.py`](../../scripts/index_notes.py) | 按篇重建（与界面共用 `index_targets`） |
| [`src/noteagent/bootstrap/settings.py`](../../src/noteagent/bootstrap/settings.py) | `CHROMA_*`、`EMBEDDING_*`、`MODEL_SETTINGS_DIR` |

包说明（与代码同步的目录表）：[`src/noteagent/retrieval/README.md`](../../src/noteagent/retrieval/README.md)。
