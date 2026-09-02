# NoteAgent 数据库

全局职责见 [architecture.md §5.3](./architecture.md#53-数据库)。本文是现行两张表的列、索引、两种读法与实例。

| 项 | 内容 |
|---|---|
| 生产库 | PostgreSQL（`DATABASE_URL` 必须 `postgresql+psycopg://`） |
| 测试库 | 内存 SQLite（`Base.metadata.create_all`） |
| 聊天装配 | [context-management.md](./context-management.md) |

PostgreSQL 只存会话与消息。笔记正文在 `notes/`；向量在 Chroma（[retrieval.md](./retrieval.md)）；待审草稿在内存 `DraftStore`。本库不写 HTTP、不调 LLM。

---

## 1. 代码落点

| 路径 | 职责 |
|------|------|
| [`src/noteagent/db/models.py`](../../src/noteagent/db/models.py) | ORM：`Base`、`Conversation`、`Message` |
| [`src/noteagent/db/engine.py`](../../src/noteagent/db/engine.py) | `create_engine_from_url`、`create_session_factory` |
| [`src/noteagent/chat/history.py`](../../src/noteagent/chat/history.py) | 唯一业务写入口 `ConversationStore` |
| [`alembic/versions/`](../../alembic/versions/) | 迁移。现行 head：`3d1c2b8a9e4f` |
| [`src/noteagent/bootstrap/app.py`](../../src/noteagent/bootstrap/app.py) | 无 `DATABASE_URL` 则 `build_container` 失败；shutdown `engine.dispose` |

依赖：`chat` 可 import `db`；`db` 不得 import `chat`。路由只调 `ConversationStore`，不 `session.add`。

`ConversationStore` 每个方法一个短生命周期 Session。`append_message` 只允许 `role ∈ {user, assistant}`。

Engine：生产 `create_engine(url)`；SQLite 开 `check_same_thread=False`，内存库 `StaticPool`，`PRAGMA foreign_keys=ON`。`sessionmaker(expire_on_commit=False, autoflush=False)`。

---

## 2. 表关系

```text
conversations 1 ──< messages
     id PK              conversation_id FK  ON DELETE CASCADE
```

删会话则消息全删。无 `users` 表（单用户本机）。压缩只改 `running_summary` 与 watermark，不删 `messages` 行，所以前端仍能画出 watermark 之前的气泡。

---

## 3. 现行表

### 3.1 `conversations`

| 列 | 类型 | 可空 | 说明 |
|----|------|------|------|
| `id` | UUID PK | 否 | 与前端 `conversation_id` / `thread_id` 相同 |
| `title` | Text | 否 | 侧栏标题；首句截断或用户重命名 |
| `created_at` | timestamptz | 否 | |
| `updated_at` | timestamptz | 否 | 写入 user/assistant 时刷新；重命名不改；写 stub 不改 |
| `running_summary` | Text | 是 | 该会话唯一摘要栏。压缩时追加，不按 Turn 拆行 |
| `summary_watermark_turn_id` | UUID | 是 | 摘要已覆盖的最后已完成 `turn_id`；新会话 `NULL` |

索引：`ix_conversations_updated_at`（侧栏倒序）。

### 3.2 `messages`

| 列 | 类型 | 可空 | 说明 |
|----|------|------|------|
| `id` | UUID PK | 否 | |
| `conversation_id` | UUID FK | 否 | → `conversations.id` CASCADE |
| `role` | Text | 否 | `user` / `assistant` / `tool` |
| `content` | Text | 否 | 气泡正文；tool 行存与 `output_preview` 相同的短文本 |
| `created_at` | timestamptz | 否 | |
| `turn_id` | UUID | 旧行可空 | 同一次用户发送 → 最终 assistant 共用 |
| `tool_name` | Text | 是 | 仅 `role=tool` |
| `tool_arguments` | Text | 是 | 参数预览（截断上限来自环境） |
| `output_preview` | Text | 是 | 工具输出前 N token（N 来自环境） |
| `truncated` | Boolean | 否，默认 false | 输出是否被截成 preview |
| `status` | Text | 是 | `ok` / `error` |

索引：`ix_messages_conversation_created`（`conversation_id`, `created_at`）；`ix_messages_conversation_turn`（`conversation_id`, `turn_id`）。

tool 行不存工具全文、不存 Agent 自我输出。截断规则见 [context-management.md §7.1](./context-management.md#71-工具循环与-stub-截断)。

---

## 4. 两种读法

| 用途 | 过滤 |
|------|------|
| 前端气泡 | `role IN ('user','assistant')`，该会话全部，按时间正序（含 watermark 之前） |
| 模型 Persistent | 该会话全部 role；watermark 为 `NULL` 则全量，否则只取 watermark **之后**的 Turn（含当前未完成 Turn） |

为什么列表滤掉 tool：气泡是给人看的对话；stub 给下一句模型和排障日志。为什么压缩不删行：侧栏要能翻出早期问答原文，摘要只服务模型窗口。

---

## 5. 实例

会话 `c1` 已把 Turn A 摘要掉；Turn B 仍在原文窗口；Turn C 进行中（刚 `list_files`）。

**conversations**

| id | title | running_summary | summary_watermark_turn_id |
|----|--------|-----------------|---------------------------|
| c1 | 注意力机制 | 用户在学 Transformer。TurnA：问了自注意力，助手给了要点。 | turnA |

再压缩一次：同一格变成「旧摘要 + 空行 + 新段落」，watermark 改为被切掉的最后一个已完成 `turn_id`。

**messages**（`conversation_id=c1`）

| id | turn_id | role | content | tool_name | tool_arguments | output_preview | truncated | status |
|----|---------|------|---------|-----------|----------------|----------------|-----------|--------|
| m1 | turnA | user | 自注意力怎么工作？ | | | | false | |
| m2 | turnA | assistant | （最终回复） | | | | false | |
| m3 | turnB | user | 和加性注意力有何差别？ | | | | false | |
| m4 | turnB | tool | （预览，最多约 N token） | read_file | `{"file_name":"Agent.md"}` | 同 content | true | ok |
| m5 | turnB | assistant | 差别是…… | | | | false | |
| m6 | turnC | user | 把刚才整理成笔记 | | | | false | |
| m7 | turnC | tool | `{"files":[...]}` | list_files | `{}` | 同 content | false | ok |

- Turn A 行仍在：前端还能画出 m1/m2；模型装配不再把它们当 Persistent 原文。
- `read_file` 全文不在表里；进程重启后只剩 preview。
- watermark 不得等于未完成的 `turnC`。
- 前端列表：m1, m2, m3, m5, m6（无 m4、m7）。

---

## 6. 不进这两张表

| 数据 | 位置 |
|------|------|
| 当前 Turn 工具全文 | 内存 Runtime，Turn 结束或进程退出即丢 |
| 待审草稿全文 | `DraftStore` |
| 已审批笔记 | `notes/*.md` |
| 检索向量 | Chroma |

---

## 7. 迁移

```text
uv run alembic upgrade head
```

现行 head `3d1c2b8a9e4f`（`down_revision = f16dee6e3c97`）。旧 `messages.turn_id` 可空，升级时按「遇到 user 开新 turn」回填。
