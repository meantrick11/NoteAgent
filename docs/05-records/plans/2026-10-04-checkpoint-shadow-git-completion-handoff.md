# Checkpoint / 影子 Git / 恢复 计划 —— 交接说明（B4 起）

本文件供新会话从 B4 继续。来源计划：[2026-10-04-checkpoint-shadow-git-completion.md](2026-10-04-checkpoint-shadow-git-completion.md)；
逐项结果与证据：[2026-10-04-checkpoint-shadow-git-completion-results.md](2026-10-04-checkpoint-shadow-git-completion-results.md)。

## 当前状态（分支 `codex/checkpoint-shadow-git-completion`，不合并／不推送）

已完成并提交（每项有测试与证据）：

| 任务 | 提交 | 说明 |
|---|---|---|
| A1—A3 + 验收修复 | `deab0a7`…`c733da9` | 阶段 A 与 review 的 S1/R1/R2/R3 已修复 |
| B1 工作区门禁与台账 | `19b5fdc` | advisory lock + maintenance；5 张表 |
| B2 影子 Git 版本 | `9351044` | `notes/versions.py` |
| B3 统一写入 | `a69a082` | `notes/mutations.py`，Library 与草稿批准接入 |
| 结果文档 | `1f56144`、`89db547` | B1—B3 证据 |

验证基线：`tests/unit tests/integration` → **590 passed, 1 skipped**。Alembic head：`e7b1c2f4a903`。

## 环境与命令

- 真实 PostgreSQL 在 `127.0.0.1:5432`（`.env` 的 `DATABASE_URL`，无 Docker）；测试用临时 schema，自动清理。
- 运行：`.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --tb=short`（在项目根）。
- `pytest` 的 `pythonpath = [".", "src", "tests"]`，故 `from scripts.xxx import` 可用。
- Alembic：`.venv\Scripts\python.exe -m alembic upgrade head`（`env.py` 读 `Settings().database_url`）。
- 前端：`cd frontend && npm run test:unit`、`npm run test:e2e`、`npm run build`（e2e 用本机 msedge）。
- 保护文件：`docs/references/思考.md`、`docs/references/亮点的地方.md`、`docs/roadmap/` 属用户个人文件，不要提交。
- 每任务循环：补失败测试 → 实现 → 重跑 → 只暂存该任务文件 → Conventional Commit（header ≤72 字符，全局 commit-msg hook）→ 回填 results。

## 已存在、B4—B9 可直接复用的件

- `recovery/models.py`：`WorkspaceState`、`MutationRecord`、`RecoveryPreview`、`RecoveryJob`、`IndexRepair`。
- `recovery/gate.py`：`WorkspaceGate.operation(mode)`（`read`/`chat` 共享，`mutate`/`recovery`/`model_rebuild` 独占）、`set_maintenance`/`clear_maintenance`/`maintenance`/`advance`/`state`。
- `notes/versions.py`：`snapshot(parent, operation_id) -> Snapshot`、`read_blob(commit, path)`、`manifests`、`resolve_ref`。
- `notes/mutations.py`：`NoteMutationService.apply(command, origin, operation_id, *, expected_hashes, retrieval)`，幂等；`_sync_index` 目前是 best-effort（B4 换持久维修）。
- `chat/agent.py`：`_write_approved` 走 mutations；`review_pending_draft`（`conversations/service.py`）持会话行锁 → 调 `apply(draft)` 闭包写盘 → 发布。
- 容器字段：`AppContainer.{workspace, versions, mutations, conversations, checkpoints}`。

## 已知需在 B5/B6 处理的耦合点

- **门禁顺序**：`review_pending_draft` 先持会话行锁、再经 `mutations.apply` 取工作区门禁，与计划「WorkspaceGate → 运行时租约 → 会话 CAS → checkpoint IO」相反。B6 的恢复协调器加门禁时必须统一（建议让草稿批准先取 gate 再锁会话，或把 gate 传入该服务）。
- **批准后清草稿非原子**：正文写入与清 checkpoint 草稿分离；B4 的维修与 B6 的持久发布要保证「批准正文已写、索引未更新」可被发现并修复。

## B4 起的分步范围（文件、机制、测试、验证命令）

### B4 可靠的单文件 RAG 更新和维修

- 文件：新增 `retrieval/repairs.py`、`tests/integration/test_index_repairs.py`；修改 `retrieval/service.py`、`retrieval/vector_store.py`、`retrieval/models.py`、`notes/mutations.py`、`bootstrap/app.py`。
- 机制：用 `IndexRepair` 台账保存正文 bytes hash、索引配置 fingerprint、状态与 operation 身份；chunk 元数据能关联同一正文版本。`index_note` 重建前后验证（无旧 chunk 残留）；`delete_note` 验证零向量；move 处理旧、新路径。空文档合法零 chunk，用台账 hash/fingerprint 证明同步，不靠 `is_indexed`。写向量前先持久标记 pending，全部写入并验证后才 ready；失败保留 repair task 并返回明确的同步待修复状态；检索按 dirty/repair 过滤或返回 index_unavailable。启动 reconciliation 与显式 retry 用相同 operation，不追加正文、不新建版本；fingerprint 变化仍走原重建与工作区门禁。
- 测试：只改 A 不重建 B、删除零向量、移动双路径、正文成功后 embed/Chroma 中断、部分 upsert、空文档、重启修复、修复前 search 不返回陈旧内容。
- 验证：`pytest tests/integration/test_index_repairs.py tests/integration/test_retrieval_service.py tests/integration/test_notes_mutations.py -q`。

### B5 纯预览计划与共享修改冲突

- 文件：新增 `recovery/planner.py`、`tests/unit/test_recovery_planner.py`；修改 `recovery/schemas.py`、`recovery/models.py`。
- 机制：以 before boundary、当前活动分支及继承历史、边界后 owned mutations、later mutations 和当前 manifest 构建 `RestorePlan`；按操作逆序求受影响路径目标 bytes／目录集合。只撤销 owned；他人后续或 external 修改即冲突（含 ABA、移动交叉路径、文件夹未追踪内容）；任一冲突 `can_apply=false`。返回 `file_changes`/`folder_changes`/`conflicts`/`affected_messages`/`requires_confirmation` 与 `state_revision`/`workspace_seq`/正文哈希/摘要/过期时间；preview 不改变正文／索引／head。
- 测试：本会话 A、他会话 B 时只撤销 A；他会话／Library／external 后改 A 整次拦截；空目录／移动／边界后批准旧草稿；无正式写入仍允许仅状态恢复；旧导入历史不可恢复。
- 验证：`pytest tests/unit/test_recovery_planner.py -q`。

### B6 整体恢复状态机、幂等重启和最后发布

- 文件：新增 `recovery/service.py`、`tests/integration/test_recovery_coordinator.py`；修改 `conversations/service.py`、`recovery/models.py`、`notes/mutations.py`、`retrieval/repairs.py`、`bootstrap/app.py`。
- 机制：`start` 在独占门禁内重新校验 preview 身份、编辑正文摘要、seq/head/hash、确认字段、冲突与有效租约；持久化确定计划与 maintenance 再执行。阶段 `prepared→restoring_files→reindexing→preparing_state→publishing→succeeded`，每路径进度持久化；恢复为不存在即删除，目录按 manifest 安全操作；生成补偿 commit 保留其他会话文件。RAG 只修受影响路径；全部正文与 index hash/fingerprint 一致后准备 fork。恢复原 UI 历史／摘要／草稿／工具，替换真实全工作区 `notes_commit`/`seq`，接受编辑后的用户消息一次。`publish_recovery` 在同一应用 DB 事务内 CAS 切换活动 branch/head/generation、发布 job 成功与 prepared_turn_id、清 maintenance。候选 checkpoint 先写但不提前可见。失败保 `failed_stage/retryable`；维修状态保留；续办相同计划，不按新现场重算。
- 测试：故障注入 `file_applied`/`git_committed`/`index_rebuilt`/`candidate_saved`/`before_publish`/`after_publish`；重复 start/retry 返回同任务／结果；LLM 失败与已成功恢复独立；原消息不重复插入。
- 验证：`pytest tests/integration/test_recovery_coordinator.py tests/integration/test_turn_recovery_pg.py -q`。

### B7 恢复 API 与 prepared-turn 重推理

- 文件：新增 `recovery/router.py`、`tests/integration/test_recovery_api.py`；修改 `chat/router.py`、`chat/schemas.py`、`bootstrap/app.py`。
- 机制：按 API-001 实现 `POST /conversations/{id}/recoveries/preview`、`POST /conversations/{id}/recoveries`、`GET /recoveries/{job_id}`、`POST /recoveries/{job_id}/retry`；写接口加 same-origin 依赖。返回 `PreviewOut`/`JobOut` 与统一 code/message/retryable；缺文件确认、preview 过期、跨会话身份、正文改变、冲突、busy 分别拒绝；客户端不能指定任意 paths/commit。`/chat` 的 `question` 与 `prepared_turn_id` 互斥（后者唯一 claim 已接受用户消息，不再 prepare）。
- 测试：确认 false 且有文件变化为 409 `confirmation_required`；冲突无正文变更；重复 prepared-turn 不重复模型调用；GET 任务在 maintenance 可用；读写入口守门禁。
- 验证：`pytest tests/integration/test_recovery_api.py tests/integration/test_checkpoint_chat_api.py -q`。

### B8 用户消息编辑、确认弹窗、冲突和进度 UI

- 文件：新增 `frontend/src/features/chat/MessageEditForm.vue`、`RecoveryConfirmDialog.vue`、`recovery.ts`、`frontend/tests/unit/message-recovery.spec.ts`、`frontend/tests/e2e/message-recovery.spec.ts`；修改 `MessageList.vue`、`UserMessageActions.vue`、`api.ts`、`store.ts`、`sse.ts` 与 Library 刷新入口。
- 注意：`c733da9`「complete checkpoint resume UI」可能已加入部分续接 UI，先检查 `store.ts`/`sse.ts`/`api.ts` 现状再补。
- 要求：每条 user 消息 16px 编辑／复制图标；编辑用服务端身份，原文进 textarea；未持久化／旧历史／忙状态给禁用原因；同时只编辑一条；Enter 换行、Ctrl/Cmd+Enter 提交、Esc 取消、IME composing 不提交；空白 trim 判空；未改内容直接关闭。提交先查未保存草稿并调 preview；`requires_confirmation=true` 弹「确认回退已执行的文件改动」与文件／目录清单及「确认回退并重新生成／取消」；conflicts 只可取消。start 前不截断历史；轮询真实 job 显示阶段与可重试错误；成功重载活动状态与 Library，用 `prepared_turn_id` 接续；刷新／切会话／旧 SSE 按 branch/generation/request token 隔离。
- 验证：`npm run test:unit`、`npm run test:e2e`、`npm run build`。

### B9 真实恢复演练、部署持久化及文档同步

- 文件：新增 `tests/integration/test_full_rollback_acceptance.py`；修改部署文件、`README.md`、`docs/01-architecture/database.md`、`docs/03-modules/chat/context-management.md`、`docs/03-modules/retrieval/retrieval.md`、模块 README、`docs/02-api/chat-tools.md`、本目录索引与结果；同步上层 `NoteAgent-docs` 仓库（只本地，不推远端）。
- 要求：notes 正文／`NOTES_HISTORY_DIR`／Chroma／PostgreSQL 均持久化；history 不嵌在 notes 内；Git 不可用返回可识别错误、不启用无历史写入。迁移运行手册（停旧 worker、备份 DB＋正文＋影子仓库、dry-run/apply、初始版本、索引核对、失败续办）。隔离持久目录做真实停／重启演练（改正文、索引失败、恢复半途停止、重开后维修续办），不得用清库重启代替。完成 G01—G16 逐条证据，跑全量回归与构建，回填真实计数与提交 SHA。
- 最终门槛与命令见计划 §6（G01—G16 表 + 全量 pytest + CLI dry-run + 前端三命令）。

## 交接保持事项

- 不合并、不推送；分支留待用户验收。
- 每任务完成即提交并回填 `2026-10-04-…-results.md`；未运行／环境不足／skip 不得记为通过。
- 上下文不足时继续写此类交接文件，保留未完成任务。
