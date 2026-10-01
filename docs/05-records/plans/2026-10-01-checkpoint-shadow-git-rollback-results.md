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
