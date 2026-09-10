# 日志与观测

全局职责见 [architecture.md §5.8](./architecture.md#58-观测)。本文是现行输出路径、三层划分、步骤文案与模块对应。切块与 Chroma 点仍以 [retrieval.md](./retrieval.md) 为准。

| 项 | 内容 |
|---|---|
| 输出 | 同一份 `var/logs/noteagent.log`（`LOG_DIR`）+ 彩色 stdout |
| 配置 | [`observability/logging.py`](../../src/noteagent/observability/logging.py)；业务文案不写在这里 |
| 不是 | 独立日志服务、把完整 prompt / 切块正文存进 PostgreSQL |

---

## 1. 要解决什么

单机排障时必须能回答：这一跳 LLM 调了没有、工具入参出参大概是什么、一篇笔记索引卡在切块还是 upsert、HTTP 和磁盘写成功没有。

同时必须守住：

- 完整 prompt、整篇笔记、切块原文 **不进聊天表**；INFO 里只留长度、截断预览或步骤名。
- 检索包不拼固定步骤字符串；索引步骤名集中在 `IndexTrace`。
- 密钥不进日志。

前端主气泡看不到工具全文和索引步骤；Chat 过程排只显示短摘要。

---

## 2. 三层怎么分

`observability/` **不是**全仓库日志的存放处。事件写在发生的模块；落到磁盘由 root logger 统一处理。

```text
setup_logging          配 handler、轮转、第三方级别
        │
        ▼
  var/logs/noteagent.log   ← 所有 logger 共用
        ▲
        │
   ┌────┴────────────────────────────┐
   │ 专用 tracer（observability）      │ 业务 _logger（各包 __name__）
   │ AgentTraceHandler  LLM/工具 hop   │ chat / notes / drafts / history …
   │ IndexTrace         索引/检索步骤  │
   └─────────────────────────────────┘
```

| 层 | 放哪 | 做什么 |
|---|---|---|
| 配置 | `observability/logging.py` | 彩色控制台、轮转文件、把 openai/httpx 等压到 WARNING |
| 专用轨迹 | `agent_trace.py`、`index_trace.py` | 跨步骤、文案要稳定的 LLM/工具/索引事件 |
| 业务事件 | 各模块 `logging.getLogger(__name__)` | HTTP、磁盘、会话、草稿、压缩、引用 |

`main.py` 启动时调 `setup_logging`。看文件：`var/logs/noteagent.log`。按 logger 名过滤（如 `noteagent.chat.agent` vs `noteagent.observability.index_trace`）。

---

## 3. AgentTraceHandler

LangChain `BaseCallbackHandler`。每次 `ChatAgent.stream` 的 `astream(..., callbacks=[AgentTraceHandler()])` 挂一个新实例。不写笔记、不写 Chroma、不写 PostgreSQL。

| 回调 | 日志 |
|---|---|
| `on_llm_start` | `LLM start  model=  prompt_chars=`（**不打完整 prompt**） |
| `on_llm_end` | `LLM end  duration=  tokens_in=  tokens_out=  reply=`（回复最多 300 字） |
| `on_llm_error` | `LLM error  duration=  error=` |
| `on_tool_start` | `Tool start  tool=  input=`（入参最多 200 字） |
| `on_tool_end` | `Tool end  tool=  duration=  output=`（出参最多 200 字） |
| `on_tool_error` | `Tool error  tool=  duration=  error=` |

`run_id` 对齐 start/end 算耗时。压缩触发、pack 体积、hop 上限在 **`chat/agent.py` 的 `_logger`**，不在本 handler。

---

## 4. IndexTrace

只打 INFO，不切块、不 embed、不写 Chroma。`RetrievalService` 在步骤边界调用；`chunker` / `embedder` / `vector_store` 自己不打索引步骤。

一次非空 `index_note`：

```text
index start file=
index delete file= elapsed_ms=     ← delete_note；从未索引过也打
note read …                        ← FileNoteRepository，logger 不同
index chunked file= chunks= chars= ← chars 是全文长度
index embedded … elapsed_ms=
index upserted … elapsed_ms=       ← 整篇重建后的全部块，不是按块增量
index done … elapsed_ms=           ← 从 start 起的总耗时
```

空切块：`index start` → `index delete` → `note read` → `index skip empty`，无 chunked/embedded/upserted/done。

只删文件：`delete_note` 只打 `index delete`。

`search`：`search query= top_k= hits= top_distance=`（聊天工具 `search_relative_from_chromadb` 会间接触发）。INFO 不打切块原文。

---

## 5. 业务模块（`__name__` logger）

| Logger | 典型事件 |
|---|---|
| `main` | 嵌入模型路径、监听地址 |
| `noteagent.bootstrap.app` | 缺 `DATABASE_URL` |
| `noteagent.llm.factory` | `LLM client model=` |
| `noteagent.chat.router` | 列会话/消息、SSE 请求、落库 assistant、审批入参 |
| `noteagent.chat.agent` | `agent stream start/end`、`context pack`、`compact trigger/skipped/refused`、hop 上限 |
| `noteagent.chat.history` | 会话 create/rename/delete、append、tool stub、load persistent、compact watermark |
| `noteagent.chat.drafts` | `draft pending/rejected/committed`、`draft indexed`、`draft index failed`、写盘失败 |
| `noteagent.chat.citations` | `citation register`、`citation sanitize` |
| `noteagent.chat.context_pack` | 材料标题树条数 |
| `noteagent.notes.router` | `notes http create/save/move/delete/index/folder *`、索引失败 exception |
| `noteagent.notes.repository` | `note list/read/write/create/delete/move`、文件夹 CRUD |
| `noteagent.prompt_eval.*` | 离线黄金集；不在 `POST /chat` 路径上 |

人审写盘成功后，同一文件里会先后出现 `drafts` 的 committed/indexed、`IndexTrace` 的 start…done、`repository` 的 `note read`/`note write`。索引失败不回滚 Markdown，日志是 `draft index failed` 或 `notes index failed`。

---

## 6. 配置

| 项 | 现行 |
|---|---|
| 目录 | `LOG_DIR`，默认 `var/logs` |
| 级别 | `LOG_LEVEL`，默认 DEBUG；文件 handler 固定 DEBUG |
| 轮转 | `noteagent.log`，5 MB × 5 份 |
| 第三方 | `openai`、`httpx`、`chromadb`、`sentence_transformers` 等 WARNING，避免完整 prompt JSON 灌进 DEBUG |

磁盘满了可删 `noteagent.log` 或整个 `logs/`，下次启动再建。不要把 `var/` 提交进 git。

排查 Agent 可搜：`LLM start`、`Tool start`、`context pack`、`compact`、`draft pending`、`draft committed`。排查索引可搜：`index start`、`index upserted`、`draft indexed`。

---

## 7. 本文件不覆盖

下列不是现行代码：

- 结构化 JSON 日志、OpenTelemetry、请求级 trace id
- 按会话把完整 prompt 落库或单独 prompt 文件
- 检索包内自拼 `index start` 文案
- 多实例日志汇聚

包内速查：[src/noteagent/observability/README.md](../../src/noteagent/observability/README.md)。运行时目录：[var/README.md](../../var/README.md)。

---

## 8. 代码落点

| 路径 | 职责 |
|---|---|
| [`observability/logging.py`](../../src/noteagent/observability/logging.py) | `setup_logging`、控制台着色 |
| [`observability/agent_trace.py`](../../src/noteagent/observability/agent_trace.py) | LLM/工具 callback |
| [`observability/index_trace.py`](../../src/noteagent/observability/index_trace.py) | 索引/检索步骤 INFO |
| [`chat/agent.py`](../../src/noteagent/chat/agent.py) | 挂 callback；pack/compact/stream 业务日志 |
| [`retrieval/service.py`](../../src/noteagent/retrieval/service.py) | 步骤边界调 `IndexTrace` |
| [`main.py`](../../main.py) | 启动时 `setup_logging` |
