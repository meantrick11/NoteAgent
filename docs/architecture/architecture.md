# NoteAgent 项目架构书

> 现行总览，按用户路径组织。细节文档只在对应小节索引。  
> 聊天工具：[chat-tools.md](./chat-tools.md)  
> 笔记草稿：[draft-generation.md](./draft-generation.md)  
> 短期记忆：[context-management.md](./context-management.md)  
> 数据库表与代码：[database.md](./database.md)  
> 屏幕/音频起源（勿实现）：[DESIGN.md](./DESIGN.md)

| 项 | 内容 |
|---|---|
| 形态 | FastAPI 单页聊天；SSE；人审后写 `notes/` |
| 现状代码 | `src/noteagent/` |
| 尚未做 | Job 状态机、URL/搜索入库、审批后自动索引、watermark 压缩 |

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构总览](#2-系统架构总览)
3. [源码结构](#3-源码结构)
4. [模块](#4-模块)
   - 4.1 [前端](#41-前端)
   - 4.2 [后端](#42-后端)
     - 4.2.1 [路由](#421-路由)
     - 4.2.2 [Agent](#422-agent)
       - 4.2.2.1 [ChatAgent](#4221-chatagent)
       - 4.2.2.2 [工具](#4222-工具)
       - 4.2.2.3 [草稿与人审](#4223-草稿与人审)
       - 4.2.2.4 [系统提示](#4224-系统提示)
       - 4.2.2.5 [上下文管理](#4225-上下文管理)
       - 4.2.2.6 [Agent 追踪](#4226-agent-追踪)
       - 4.2.2.7 [LLM](#4227-llm)
       - 4.2.2.8 [RAG](#4228-rag)
   - 4.3 [数据库](#43-数据库) → [database.md](./database.md)
   - 4.4 [笔记](#44-笔记)
5. [数据流（现状）](#5-数据流现状)
6. [历史方案](#6-历史方案)

---

## 1. 项目概述

个人学习笔记助手：在对话里整理值得保留的内容，经前端审批后写入 Markdown。检索是手动索引后的粗 RAG。

与代码一致的原则：LLM 只出提案；写文件只走 `commit_review`；用户可见历史只在 PostgreSQL 的 user / assistant 行。

---

## 2. 系统架构总览

```text
前端 home.html
    │  侧栏 / 气泡 / SSE / 草稿卡片 / 离开页
    ▼
后端路由 chat/router.py
    ├── 会话 CRUD、落库 user/assistant     →  4.3 数据库
    └── ChatAgent（LLM + 工具 + RAG + 草稿）
            只读 notes / search；propose 进内存
            人审后 commit_review            →  4.4 笔记
```

---

## 3. 源码结构

```text
src/noteagent/
  bootstrap/     Settings、AppContainer、FastAPI
  chat/          Agent、工具、草稿、路由、会话写入口
  db/            ORM 与 engine（无 HTTP/LLM）
  notes/         Markdown IO
  retrieval/     切块、embedding、Chroma（Agent RAG）
  llm/           DeepSeek Chat 模型工厂（Agent 用）
  observability/ 进程日志、LLM/工具回调
  web/           HTML 模板
main.py          读配置、打日志、uvicorn
alembic/         迁移（会话表）
notes/           正式笔记数据
```

依赖：`chat` 可调 `notes`、`retrieval`、`llm`、`observability`、`db`。`notes` / `retrieval` / `db` 不得 import `chat`。

---

## 4. 模块

按用户可见路径：前端 → 后端（先路由再 Agent）→ 会话库 → 笔记文件。装配与进程日志不单独成章。

### 4.1 前端

文件：[`web/templates/home.html`](../../src/noteagent/web/templates/home.html)，由 `GET /` 下发。单页：侧栏会话 + 主栏气泡 + 底栏输入。无独立前端工程。

| 路径 | 前端行为 | 打到 |
|------|----------|------|
| 进页 / 切会话 | `loadConversations`；点会话再拉消息气泡 | `GET /conversations`、`GET /conversations/{id}/messages` |
| 发一句 | 立刻画 user 气泡和空 assistant；`fetch("/chat")` 读 SSE：`conversation` 记下 id 并刷新侧栏，字符串当 token 用 marked 渲染，`draft` 出卡片 | `POST /chat` |
| 审草稿 | 卡片：同意 / 拒；create/append 还可改追加到所选 / 改为新建；replace/delete 仅同意或拒绝 | `POST /chat/review`；结果再画一条 assistant（已写入 / 已删除 / 已取消） |
| 离开 | `visibilitychange=hidden` 或 `beforeunload`：`sendBeacon("/chat/user_exit")` | `POST /chat/user_exit` |

侧栏还可 PATCH 重命名、DELETE 删除。气泡只渲染 user / assistant；工具过程不展示。`isStreaming` 期间不能连发。

---

### 4.2 后端

HTTP 在路由；模型循环在 Agent。路由不自己调 LLM。

#### 4.2.1 路由

文件：[`chat/router.py`](../../src/noteagent/chat/router.py)、[`chat/schemas.py`](../../src/noteagent/chat/schemas.py)

`APIRouter` 由 `create_app` `include_router`。依赖从 `request.app.state.container` 取 `history` / `chat_agent`。`POST /chat` 用 Depends `resolve_conversation`：未知 id 在 SSE 前 404；无 id 则 `create`，标题来自首句截断。

**请求/响应模型**

| 模型 | 用途 |
|------|------|
| `RequestModel` | `/chat`、`/chat/user_exit`：`question`；可选 `conversation_id` / `thread_id`（优先 conversation_id） |
| `ReviewRequest` | `/chat/review`：`thread_id`、`action`；override 时 `write_action`、`file_name` |
| `RenameConversation` | PATCH：`title` |
| `ConversationOut` | 会话摘要：id、title、updated_at |
| `MessageOut` | 气泡：id、role、content、created_at |

| 方法 | 路径 | 行为 |
|------|------|------|
| GET | `/` | 下发 4.1 页面 |
| GET | `/conversations` | 侧栏，按 `updated_at` 倒序 |
| GET | `/conversations/{id}/messages` | 气泡正序；缺会话 404 |
| PATCH | `/conversations/{id}` | 重命名；空标题/过长 400；缺会话 404；不改 `updated_at` |
| DELETE | `/conversations/{id}` | 204，CASCADE 消息；缺会话 404 |
| POST | `/chat` | `append_message` user → SSE `conversation` / `token` / `draft` → 拼接 token 后 `append_message` assistant |
| POST | `/chat/review` | `ChatAgent.review` → `commit_review` |
| POST | `/chat/user_exit` | `summarize_on_exit`；`{status: finished}` |

SSE：`EventSourceResponse`。`conversation` 的 data 为 `{id, title}`；`token` 为字符串增量；`draft` 为 pending 卡片。空 data 不 yield。

#### 4.2.2 Agent

运行时：`create_agent`（LangChain）+ 四个 Tool + `system.txt`。LLM 与 RAG 都是 Agent 能力，不单独成顶层模块。

##### 4.2.2.1 ChatAgent

文件：[`chat/agent.py`](../../src/noteagent/chat/agent.py)

| 方法 | 行为 |
|------|------|
| `stream(question, thread_id, turn_id)` | `contextvars` 写入 `current_thread_id` / `current_turn_id`；`bind_tools` 循环装配 watermark 后 Persistent + summary + 当前 Runtime；每步工具写 stub；`astream` 吐 token；结束后若有 pending draft 再 yield `draft` |
| `review(...)` | 转到 `commit_review` |
| `summarize_on_exit` | 空实现，只打日志，**不写** `context.md` |

Checkpoint：**现状**无 `InMemorySaver` / `create_agent` 跨 Turn 记忆；当前 Turn 全文只在本次 `stream()` 局部列表。进程重启后模型上下文从 PG 的 Persistent + `running_summary` 重建，UI 历史仍在 PG。目标见 4.2.2.5。

##### 4.2.2.2 工具

契约全文：[chat-tools.md](./chat-tools.md)（工作流、参数、意图门、人审）。装配：[`chat/tools.py`](../../src/noteagent/chat/tools.py) `build_chat_tools(notes, retrieval, drafts)`。

| 名称 | 作用 | 副作用 |
|------|------|--------|
| `list_files` | `notes.list_notes()` | 无写盘 |
| `read_file` | `notes.read` | 无写盘 |
| `search_relative_from_chromadb` | `retrieval.search(query, top_k=3)` | 无写盘 |
| `propose_note` | 校验四动作后 `DraftStore.put` | **不写磁盘** |

Hop / stub：[context-management.md §7.1](./context-management.md#71-工具循环与-stub-截断代码现状)。

##### 4.2.2.3 草稿与人审

文件：[`chat/drafts.py`](../../src/noteagent/chat/drafts.py)。细节：[chat-tools.md](./chat-tools.md) §5–§6。

- 每会话一份 pending `NoteDraft`（`DraftStore`，重启丢失）。
- `propose_note` 不写盘；`commit_review` 才 `create` / `write` / `delete`。
- HTTP：`POST /chat/review`。目标 Job/ChangeSet 见 [draft-generation.md](./draft-generation.md)。

##### 4.2.2.4 系统提示

文件：[`chat/prompts/system.txt`](../../src/noteagent/chat/prompts/system.txt)。历次全文：[`prompts/iterations/`](../../src/noteagent/chat/prompts/iterations/README.md)（v1–v7）。

约定：人审后才落盘；闲聊不 `propose_note`；意图不清先问、再提案；记笔记正文按忠实/完整/结构/流畅/形态/可检索；材料已有章节标题则原文含编号映射层级；问旧知识先 search；提案前 list/核对；回复不粘贴完整草稿。人工评测集见仓库根目录 [`evals/`](../../evals/README.md)。

##### 4.2.2.5 上下文管理

**不是**旧架构的 `agent/context.py` 滑动窗口。

**代码现状：** 跨回合 = watermark 后的 Persistent（user + 最终 assistant + tool stub）+ 会话 `running_summary`；当前 Turn 工具全文只活在本次 `stream()` 局部 Runtime；退出 `summarize_on_exit` 为空实现，不写 `context.md`。

**目标契约（实现前勿按旧滑动窗口写）：** [context-management.md](./context-management.md)

| 内容 | 章节 |
|------|------|
| Turn、四层存储、外部/内部 Context | [§1–2](./context-management.md#1-要解决什么) |
| 需求与明确不做 | [§3](./context-management.md#3-需求) |
| turn_id、stub、watermark | [§4](./context-management.md#4-数据落地逻辑不强制拆表) |
| K=T−F、80% 触发、60% 目标、完整 Turn 切割 | [§5](./context-management.md#5-压缩算法) |
| 流程图 | [§6](./context-management.md#6-流程图) |
| 与 agent/history 的改动面 | [§7](./context-management.md#7-与现有模块的接口)（含 §7.1 工具循环） |
| 验收 | [§8](./context-management.md#8-验收) |
| 决策表 | [§9](./context-management.md#9-决策记录问题--否决--敲定) |

备忘（非契约）：[`docs/experience/context/`](../experience/README.md)。

##### 4.2.2.6 Agent 追踪

文件：[`observability/agent_trace.py`](../../src/noteagent/observability/agent_trace.py)

`AgentTraceHandler` 挂在每次 `stream` 的 `callbacks`：LLM start/end（token 用量、回复预览截断）、Tool start/end（入参/出参截断、耗时）。不把完整 prompt 当聊天消息存库。

##### 4.2.2.7 LLM

文件：[`llm/factory.py`](../../src/noteagent/llm/factory.py)

`create_chat_model(settings)`：`init_chat_model`，`model_provider=deepseek`，模型名默认 `deepseek-v4-flash`，密钥 `DEEPSEEK_API_KEY`，可选 `DEEPSEEK_API_BASE`。只给 `ChatAgent` 用；路由不直连模型。

##### 4.2.2.8 RAG

包：[`retrieval/`](../../src/noteagent/retrieval/README.md)。聊天侧入口只有工具 `search_relative_from_chromadb`。

| 类 | 职责 |
|----|------|
| `MarkdownChunker` | `RecursiveCharacterTextSplitter`，chunk 500、overlap 50，中文标点分隔 |
| `SentenceTransformerEmbedder` | 本地模型，路径来自 Settings |
| `ChromaVectorStore` | PersistentClient upsert / query |
| `RetrievalService` | `index_note(file)` → 切块、embed、id=`{file}_{i}`；`search` 返回 `SearchHit(content, distance, metadata)` |
| 脚本 | `scripts/index_notes.py` 手动索引 |

审批后**不会**自动 index。目标检索形态见 [draft-generation.md §6](./draft-generation.md#6-检索)。

---

### 4.3 数据库

全文：[database.md](./database.md)（现行两表、目标列、实例行、Store / Alembic）。

包：[`db/`](../../src/noteagent/db/README.md)。PostgreSQL 只存会话与消息，不写 HTTP、不调 LLM。业务写入口仅 `ConversationStore`。缺 `DATABASE_URL` 时 `build_container` 失败。

**现状：** 同两表已含 `running_summary`、watermark、`turn_id`、tool stub；压缩不删旧行。Alembic head `3d1c2b8a9e4f`。细节与实例见 [database.md](./database.md)。上下文行为以 [context-management.md](./context-management.md) 为准。

---

### 4.4 笔记

包：[`notes/repository.py`](../../src/noteagent/notes/repository.py)。这是人审之后的正式知识落盘，不是聊天历史。

`FileNoteRepository`：根目录默认 `notes/`。`list_notes` / `read` / `create`（写 `# title`）/ `write`（默认追加，可覆盖）/ `delete` / `exists`。`NotePathError` 拒绝空名、绝对路径、`..`、子目录。Agent 工具只读列表与内容；真正 `create`/`write`/`delete` 仅 `commit_review`。聊天记忆不写 `context.md`。

---

## 5. 数据流（现状）

```text
进页 → GET 会话列表 / 消息 → 只画 user、assistant
发一句 → POST /chat
  → PG append user（带 turn_id）
  → ChatAgent.stream（watermark 后 Persistent + running_summary；当前 Turn Runtime 全文）
  → SSE token；可选 SSE draft
  → PG append assistant（仅最终可见正文）
审草稿 → POST /chat/review → commit_review → notes/ 文件
离开页 → POST /chat/user_exit → 空实现（不写 context.md）
```

目标压缩流：[context-management.md §6](./context-management.md#6-流程图)。  
目标 Job/自动索引：[draft-generation.md §2](./draft-generation.md#2-端到端工作流目标)。

---

## 6. 历史方案

截图、Whisper、pHash、三个屏幕 Tool，见 [DESIGN.md](./DESIGN.md)。本文第 4 章只对应当前 `src/noteagent` 包。
