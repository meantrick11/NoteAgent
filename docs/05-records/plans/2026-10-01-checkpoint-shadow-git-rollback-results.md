# Checkpoint 影子 Git 回退实施结果记录

对应计划：[2026-10-01-checkpoint-shadow-git-rollback.md](2026-10-01-checkpoint-shadow-git-rollback.md)

本文件逐任务记录「实现 / 已验证 / 失败 / 未运行」，只写实际跑过的命令与结果，不抄旧测试数量当新证据。
状态标记：`未开始` / `进行中` / `已完成` / `阻塞`。

执行分支：`feat/checkpoint-shadow-git-rollback`

---

## Task 0：执行基线、合同与测试夹具（已完成）

### 基线快照（2026-10-01）

| 项 | 值 |
|---|---|
| 工程仓库 HEAD | `59c23210cf85138d5a851771f1c8d5f74e652b0f` |
| 上层仓库 HEAD | `7920169e44a0e6d3e3215916c71fcdc0e173b7e2` |
| Python | 3.13.5 |
| Node | v22.16.0 |
| Git | 2.52.0.windows.1 |
| PostgreSQL | 18.4（库 `noteagent`，127.0.0.1:5432 可连接） |
| `TODO.md` blob | `cb4af66c603ce66ccbef78e8aa9f6d6b74e12d98` |
| `docs/references` 树 | `a79ac0e477fa4d79b37155634201189ce5061fc4` |
| 受保护 tag | `docs-v1.5.0`、`docs-v1.5.1`、`v1.0.0`、`snapshot-pre-pending-draft` |

工作区状态：`git status --short` 共 100 条，均为此前「四目录文档迁移」尚未提交的
`docs/` 变更（`R/D`）与新增目录（`??`）。**本次执行不 reset / clean，保留既有差异。**

### 依赖变更

`uv add langgraph-checkpoint-postgres "psycopg[binary,pool]"`：

- 新增 `langgraph-checkpoint-postgres==3.1.2`、`psycopg-pool==3.3.3`；
- 锁定版本无变化（`langgraph==1.2.5`、`langgraph-checkpoint==4.1.1`、`langchain-core==1.4.7` 不变）；
- `uv.lock` 仅新增 2 个 package 条目，无既有条目版本改动。

### 基线测试（改动前）

```text
Backend: .venv/Scripts/python.exe -m pytest \
  tests/unit/test_chat_history.py tests/unit/test_context_pack.py \
  tests/unit/test_context_compact.py tests/unit/test_drafts.py \
  tests/integration/test_app.py tests/integration/test_notes_api.py -q
=> 104 passed, 1 warning in 15.59s

Frontend: npm --prefix frontend run test:unit -- \
  tests/unit/chat-state.spec.ts tests/unit/sse.spec.ts
=> Test Files 2 passed (2) / Tests 38 passed (38)
```

### 未运行

- 上层文档修订：见「上层文档」小节。
- `recovery_harness` / `conversation_harness` / `postgres_harness` 的完整实现随 Task 1/2/6/8 落地后补齐并立即运行。

### 交付物

| 文件 | 内容 |
|---|---|
| `tests/support/fakes.py` | `FakeEmbedder`（哈希定长向量）、`FakeRetrieval`、`FailInjector`（六阶段一次性故障注入，含 `FAULT_STAGES`） |
| `tests/support/__init__.py` | 测试专用包说明 |
| `tests/conftest.py` | `postgres_dsn`（连不通即失败，不 skip）、`pg_schema`（一次性 schema + `search_path` DSN）、`tmp_notes`、`fake_embedder`、`fail_stage`；`_MaskedDsn` 保证 DSN 密码不进测试输出 |
| `tests/unit/test_test_support.py` | 5 例：嵌入确定性、故障一次性/顺序/未知阶段拒绝、阶段常量与 §5.5 一致 |
| `tests/integration/test_postgres_schema.py` | 2 例：schema 隔离、不与其他 schema 共享表 |
| `pyproject.toml` | `pythonpath` 增加 `tests`（供 `from support.fakes import ...`）；新增 checkpoint 依赖 |

### 新增测试结果

```text
pytest tests/unit/test_test_support.py tests/integration/test_postgres_schema.py -q
=> 7 passed in 0.49s

回归（基线选择集 + 新增）：111 passed, 1 warning in 5.27s
```

### 上层文档修订

已获用户批准修改上层仓库 `NoteAgent-docs`（HEAD `7920169`）：

| 文档 | 版本 | 变更 |
|---|---|---|
| `REQ-018` | 1.0.0 → 1.1.0 | 补充冲突拦截/保留后续更改、文件变化确认弹窗、按操作撤销、复制/编辑图标、编辑语义与失败区分；确认冲突策略 |
| `API-001` | 1.0.0 → 1.1.0 | 同步恢复路由、PreviewOut/JobOut 字段与错误码、读接口兼容增强、复制/编辑契约 |
| `DATA-001` | 1.0.0 → 1.1.0 | 正文级哈希、按操作撤销与冲突归属、空文件零片段、prepared turn 幂等 |
| `TC-REQ-018-001` | 1.0.0 → 1.1.0 | 冲突策略确认；新增复制、文件变化确认、空文件、prepared turn、失败注入矩阵场景 |
| `CR-2026-001` | 1.0.0 → 1.1.0 | 记录本轮执行授权 |
| `CHANGELOG.md` | — | 追加本轮小节 |

所有文档 `status` 保持 `review`，未创建发布基线或 Tag，未虚构评审人员。

### 自检（Task 1～12 公共类型与夹具一致性）

- `FAULT_STAGES` 与计划 §5.5 阶段序列一致，由 `test_fault_stages_match_recovery_protocol` 锁定。
- `postgres_dsn`/`pg_schema` 供 Task 1 `postgres_harness` 复用；`tmp_notes`/`fake_embedder` 供 Task 1/2 复用；`fail_stage` 供 Task 6/8 复用。
- `conversation_harness`（需真实图 + InMemorySaver）与 `recovery_harness`（需影子 Git/Chroma）依赖尚未实现的生产模块，按计划「随对应任务补齐后立即跑测试」，不在 Task 0 写空 stub。

### 失败 / 未运行项

- 无失败项。
- `conversation_harness`、`postgres_harness`、`recovery_harness`、`rollbackApp` 尚未实现（依赖生产模块），未运行。

---

## Task 1（A）：会话记录拆分、元数据与 PostgreSQL saver（已完成）

### 交付物

| 文件 | 内容 |
|---|---|
| `src/noteagent/conversations/records.py` | 迁出 `MessageRecord`/`ConversationRecord`；新增持久化 `GraphState` schema（`STATE_SCHEMA_VERSION=1`）、`initial_state`、`validate_state`、显示记录转换 |
| `src/noteagent/conversations/models.py` | `conversation_branches`/`conversation_runs`/`user_message_boundaries` ORM，`Base` 来自 `db` |
| `src/noteagent/conversations/checkpoints.py` | `CheckpointRuntime`（open/close、`from_conn_string`/`attached`）、`thread_config`（固定 ns + 显式 checkpoint_id）、`postgres_uri`、`state_to_checkpoint` |
| `src/noteagent/conversations/service.py` | `ConversationService`：创建会话（元数据 + 根分支 + 首个安全 checkpoint）、活动 head 查询、状态读写、head 发布 |
| `src/noteagent/conversations/{__init__.py,README.md}` | 公共导出与模块说明 |
| `alembic/versions/b1e7c4a90d23_conversation_branches_runs_boundaries.py` | 扩展 conversations 四列 + 三张新表；可 upgrade/downgrade |
| `tests/support/harness.py` | `ConversationHarness`：同一接口支持 SQLite+InMemorySaver 与真实 PostgreSQL+AsyncPostgresSaver，可 `reopen()` |
| `tests/unit/test_conversation_state.py` | 9 例 |
| `tests/integration/test_postgres_checkpoints.py` | 4 例 |

修改：`chat/history.py`（DTO 改为从 `conversations.records` 导入并保留再导出）、`chat/context_pack.py`、`chat/context_compact.py`（类型依赖迁出 history）、`db/models.py`（Conversation 新增 `active_branch_id`/`generation`/`state_backend`/`migration_batch_id`）、`db/__init__.py`（`load_all_models()` 惰性导入）、`alembic/env.py`、`bootstrap/app.py`（容器新增 `conversations`/`checkpoints`，lifespan 打开/关闭 saver）、`tests/conftest.py`、`tests/integration/test_postgres_schema.py`。

### 已运行检查

```text
pytest tests/unit/test_conversation_state.py -q
=> 9 passed in 0.29s

pytest tests/integration/test_postgres_checkpoints.py tests/integration/test_postgres_schema.py -q
=> 7 passed in 2.17s

pytest tests/unit tests/integration -q          # 全量回归
=> 523 passed, 1 warning in 25.30s
```

迁移（隔离 schema，未触碰开发库 public）：

```text
DATABASE_URL=<...>?options=-csearch_path%3Dt_mig_... alembic upgrade head
=> 5 个 revision 全链路成功；新表 conversation_branches/conversation_runs/
   user_message_boundaries 与 conversations 新列均存在
alembic downgrade -1
=> 仅剩 alembic_version/conversations/messages；随后 drop schema
```

PostgreSQL 测试真实执行了关闭/重连（`reopen()`），验证 state 与 head 跨连接持久；内存 saver 走同一 `ConversationService` 接口。

### 与计划的偏差（已核实，非静默改动）

1. **`GraphState` 落在 `conversations/records.py`**，而非计划 §3 的 `chat/graph.py`。原因：Task 1 在任何图存在之前就需要该 schema，且避免 `chat → conversations` 反向依赖。Task 2 的 `chat/graph.py` 将导入它。
2. **`active_branch_id` 不加数据库外键**：`conversations` 与 `conversation_branches` 互指会形成 DDL 循环依赖，改为应用层维护（§4.2 也只要求字段本身）。
3. **`db/models.py` 在本任务修改**（计划把该文件列在 Task 3）：扩展列是该任务的 migration 必需的，否则 revision 与应用模型不一致。
4. **`alembic/env.py` 修复了一个既有缺陷**：`config.set_main_option` 遇到 URL 中的 `%` 会因 configparser 插值报错；现对 `%` 转义。这影响任何含百分号编码的 URL。
5. **§4.3 的 `prepare_turn`/`fork_for_edit`/`publish_recovery` 未在本任务实现**：它们分别依赖图（Task 2）与恢复模块（Task 8）。本任务只交付可在无图条件下验证的元数据/状态读写。
6. **Windows 事件循环约束**：psycopg 异步驱动拒绝默认 `ProactorEventLoop`，测试在 `conftest.py` 设置 `WindowsSelectorEventLoopPolicy`；生产镜像为 Linux，不受影响。已记录，未改动生产代码。

### 失败 / 未运行项

- 无失败项。
- 未在开发库 `noteagent` 的 `public` schema 上执行 migration（避免改动共享状态）；迁移正确性已在一次性 schema 上验证 upgrade + downgrade。
- `chat/graph.py` 尚未存在，故「真实图 update_state fork」夹具（Task 0 约定）延后到 Task 2；本任务用 `write_state(publish=False)` 表达同一「未发布候选」语义。

---

## Task 2（A）：将 Agent 循环改为可持久化图执行（进行中）

本任务按计划允许的方式拆成两个提交，先落地**图核心**（可独立验证），再切换 `ChatAgent.stream` 的运行路径。

### 已完成：图核心（提交 1）

| 文件 | 内容 |
|---|---|
| `src/noteagent/chat/graph.py` | `build_chat_graph`：`START→compact→model→(tools→compact→model)*→finalize→END`；`stream_graph` 以 `stream_mode=["custom","updates"]` 转发节点事件，并保证 run 结束时 saver 已落盘 |
| `src/noteagent/chat/nodes.py` | `GraphRuntime` 与四个节点；节点只依赖 checkpoint 状态，不读旧表；tools 节点在执行期间才设置 `current_thread_id/current_turn_id/current_citations` 局部上下文 |
| `src/noteagent/chat/events.py` | 既有 SSE 合同的唯一映射处（thinking/generating/token/think/tool/tool_done/sources/assistant_final/draft/error） |
| `conversations/service.py` | 新增 `prepare_turn`（在会话 CAS 下写 user 消息 + 登记 boundary + 占位 ConversationRun 防重复）与 `mark_run` |
| `conversations/checkpoints.py` | `state_to_checkpoint` + `next_versions`（版本必须由 saver 生成） |
| `conversations/records.py` | `GraphState` 增加 `announced_tool_ids`；新增 `message_dict_from_record` |
| `chat/citations.py` | `CitationRegistry.as_list/from_list`，使引用注册表随 checkpoint 往返 |
| `tests/unit/test_chat_graph.py` | 6 例 |

### 已运行检查

```text
pytest tests/unit/test_chat_graph.py -q
=> 6 passed in 0.53s

pytest tests/unit tests/integration -q        # 全量回归
=> 529 passed, 1 warning in 23.13s
```

覆盖：单跳轮次写入 user+assistant、多次工具跳的调用/结果配对与「工具跳 prose 只进 trace」、hop 上限触发失败收尾（不伪造成功）、压缩保留展示历史、`propose_note` 草稿随状态保存且不写盘、同一 `request_id` 只允许一次 prepare。

### 本任务踩到的实现约束（已验证）

1. **checkpoint 的 `channel_versions` 必须由 saver 的 `get_next_version` 生成**：自己填 UUID 或整数会让下一个 superstep 在 `get_new_channel_versions` 里抛错（类型/格式不匹配）。`next_versions()` 集中处理。
2. **LangGraph 会向声明了第二个参数的节点注入自己的 `Runtime`**：最初用 `functools.partial(node, runtime=...)` 直接报 `'Runtime' object has no attribute ...`。改为单参数闭包绑定。
3. **工具结果不能被当成最终回答**：`ToolMessage` 有 content 且没有 `tool_calls`，`_final_answer` 必须显式排除它，否则 hop 上限会用工具输出冒充回答、把失败标成成功。
4. **计划里的压缩代表用例需要 ≥2 个已完成的历史轮次**：`select_turns_to_drop` 永远保留最新的完整轮次，因此「第 2 轮触发压缩」时没有可丢弃轮次，`running_summary` 不会产生。测试改为 3 轮（第 3 轮 force_compact），语义与计划一致；未修改压缩算法本身。

### 尚未完成（提交 2）

- `ChatAgent.stream` 尚未切换到图；HTTP/SSE 与旧 `ConversationStore` 运行路径仍按现状工作，`test_chat_agent_context.py` 未被改动。
- 原因是该切换的爆炸半径包含 `prompt_eval/run.py`、`rag_eval/agent_run.py` 与 `bootstrap/runtime.py` 的装配，而评测运行器按计划归属 Task 3。计划本身也要求 A 阶段整体验收前不得把编辑入口开放给半迁移后端。
- 因此本提交只交付「真实图 + 真实 checkpoint 可运行且行为有测试锁定」，**不声称 Task 2 完成**。

## 2026-10-02 验收问题修复补充

Codex 根据验收记录修复了并发认领／head CAS、准备失败重试、checkpoint 草稿来源、运行终态、明确节点位置及中断续跑；补充数据库租约、旧执行者 fencing 和异步流清理，并修复回归发现的模型重建门禁竞争。完整后端回归：**552 passed，1 warning**。

具体改动、迁移约束及仍未完成的原计划范围见：[修复记录](2026-10-02-checkpoint-shadow-git-rollback-fixes.md)。本补充不改变 Task 2“进行中”的整体状态，不把正式 HTTP 切换或阶段 B 计为已完成。
