# NoteAgent 数据库

全局职责见 [architecture.md §5.7](architecture.md#57-数据库)。当前权威会话状态为 checkpoint，应用表负责元数据和恢复协调。下面原 Conversation/Message 字典仅用于旧数据迁移核对，不再作为正式消息写入协议。

| 项 | 内容 |
|
## 当前持久层

| 存储 | 权威数据 |
|---|---|
| LangGraph PostgreSQL saver | GraphState：ui_messages、working_records、摘要、草稿、本轮工具消息、notes_commit/seq |
| conversations / conversation_branches | 元数据、state_backend、active branch/head、generation、revision |
| conversation_runs / user_message_boundaries | 持久输入身份、接受前安全 checkpoint、运行租约与可恢复边界 |
| workspace_state | seq、current_commit 与持久 maintenance |
| mutation_records | operation、归属、路径/目录前像、前后 commit、writing/applied/published/failed |
| recovery_previews / recovery_jobs | 确认计划、编辑摘要、候选、prepared turn 与失败阶段 |
| index_repairs | 正文哈希、索引配置、pending/ready/failed 与重试信息 |

应用表由 Alembic 管理，saver 的表由 runtime.setup 生命周期管理。事务边界见 [恢复实现](../03-modules/recovery/recovery.md)；不能把 saver 写入与应用事务当作自动原子。旧 messages、摘要/草稿列只用于 legacy 数据读取或导入。

源码入口见 [源码导航](../../src/NoteAgent/README.md) 和 [数据库基础设施](../../src/NoteAgent/TechnicalSupport/DatabaseAccess/README.md)。

## 旧数据字典（迁移参考）

---|---|
| 生产库 | PostgreSQL（`DATABASE_URL` 必须 `postgresql+psycopg://`） |
| 测试库 | 内存 SQLite（`Base.metadata.create_all`） |
| 聊天装配 | [context-management.md](../03-modules/chat/context-management.md) |

PostgreSQL 存会话、消息和待审草稿 JSON。笔记正文在 `notes/`；向量在 Chroma（[retrieval.md](../03-modules/retrieval/retrieval.md)）。本库不写 HTTP、不调 LLM。

---

## 1. 代码落点

| 路径 | 职责 |
|------|------|
| [BusinessModules/ConversationState/ConversationModels.py](../../src/NoteAgent/BusinessModules/ConversationState/ConversationModels.py) | ORM：`Base`、`Conversation`、`Message` |
| [TechnicalSupport/DatabaseAccess/DatabaseEngine.py](../../src/NoteAgent/TechnicalSupport/DatabaseAccess/DatabaseEngine.py) | `create_engine_from_url`、`create_session_factory` |
| [BusinessModules/ConversationState/LegacyConversationCompatibility/LegacyConversationStore.py](../../src/NoteAgent/BusinessModules/ConversationState/LegacyConversationCompatibility/LegacyConversationStore.py) | 旧消息表兼容与侧栏元数据 `ConversationStore` |
| [`alembic/versions/`](../../alembic/versions) | 迁移。现行 head：`e7b1c2f4a903` |
| [AppBootstrap/HttpApp.py](../../src/NoteAgent/AppBootstrap/HttpApp.py) | 无 `DATABASE_URL` 则 `build_container` 失败；shutdown `engine.dispose` |

依赖：`chat` 可 import `db`；`db` 不得 import `chat`。现行会话通过 ConversationService 发布 checkpoint；旧表与侧栏元数据使用 ConversationStore。

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
| `pending_draft` | JSON | 是 | 待审 `NoteDraft`；有值须人审，批准/拒绝后 `NULL` |

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
| `citations` | JSON | 是 | 仅 assistant：本条实际引用 `[{index, file_name, chunk_index, quote}]`，index 按该条正文首次出现为 1..n |

索引：`ix_messages_conversation_created`（`conversation_id`, `created_at`）；`ix_messages_conversation_turn`（`conversation_id`, `turn_id`）。

tool 行不存工具全文、不存 Agent 自我输出。截断规则见 [context-management.md §7.1](../03-modules/chat/context-management.md#71-工具循环与-stub-截断)。

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
| 已审批笔记 | `notes/*.md` |
| 检索向量 | Chroma |

---

## 7. 迁移

```text
uv run alembic upgrade head
```

旧消息表阶段 head `a9b4c2d1e8f0`（`down_revision = 8c2e1a4b7d90`）。`conversations.pending_draft` 可空 JSON。此前 `messages.citations` 可空 JSON，仅 assistant 最终消息写入实际引用。旧 `messages.turn_id` 可空，升级时按「遇到 user 开新 turn」回填。
