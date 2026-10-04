# Checkpoint、影子 Git 与 RAG 整体回退修复／完成计划 —— 执行结果

## 最终合并状态（2026-10-04）

代码已合并并推送 origin/main，合并提交 7ac64ee（包含合并前草稿保存竞态修复 68f59c0）。上层 NoteAgent-docs 已本地提交，未推送。旧评审与原 B1–B9 记录保留追溯，不能将下文早期“未合并/推送”或旧测试数字作为最终状态。

最终证据：后端全量 647 passed/1 skipped；前端完整端到端 64 passed；合并前保存锁补修后 145 单测、8 项相关端到端和构建通过。真实 PG/Git/Chroma 重启与双进程故障演练已完成；Docker 镜像未构建运行。前端总览与工具契约已同步 checkpoint、统一审批、更名与直接追加流程。


## 2026-10-04 Codex 首轮补验结论（历史记录）

B1–B9 原自报未达标部分已修复并独立复审。代码与实现文档提交 **ea6bb8c**，上层文档独立仓库提交 **eb59aa5**。本地提交，没有合并或推送；原评审和以下 B1–B9 原记录保留追溯。

| 验证 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q` | **646 passed, 1 skipped**，194.98s |
| `npm run test:unit` | **143 passed** |
| `npx playwright test --workers=2` | **61 passed**，49.1s |
| `npm run build` | 通过 |
| G12/G14 | 真实 PostgreSQL saver/Git/Chroma 子进程终止/重启与双进程锁竞争通过，含在后端全量内 |
| G16 | 持久卷/备份、双仓文档追溯 | 通过（Docker 未运行） | Git/持久 history 卷静态检查；真实 PG/Git/Chroma 重启；上层仓库 eb59aa5 与 CR-2026-004 |
| Docker | 运行镜像补装 Git、Compose 独立 notes_history 卷，静态检查通过；**未构建/运行镜像** |

### 前轮缺陷闭环

- S-B01/02：read/chat shared 与 mutate/recovery/model_rebuild exclusive 门禁接正式 runtime，异步依赖覆盖 HTTP/SSE 生命周期；工具 search_synced、启动 reconcile 与显式单文件 index 更新持久维修台账。
- S-B03/04/08：独占内读取前像/校验，Git 失败完整补偿 CREATE/MOVE/目录重命名；retained ref 发布不重复 append；writing 与 maintenance 同事务，worker 死亡后其他写拒绝，补偿不会误删后来已成功写入。
- S-B05：生产 Git 不可用关闭写入；legacy draft/review 409，先迁移，不能旁路无历史审批。
- S-B06、R-B01：副作用前校验 URL 会话、revision、seq、编辑/正文/目录摘要、TTL、确认；预览前外部修改与预览后新附件都冲突，保留后续 Library 改动。
- S-B07：owner/token 隔离迟到预览与 start/poll；prepared 生成绑定 job 会话；刷新或 start 报错后接回持久 job，对话框提供可点击 retry（新增 E2E）。
- R-B02：索引全部 synced 才发布；校验整文件哈希、配置指纹、全部片段内容/数量/偏移，缺片段也过滤和维修；失败保持维护。
- R-B03/05/06：候选 fork 幂等复用 user/boundary/run ID，generation 一致；prepared claim 前验证会话/revision；已接受 prepared 不因 60 秒租约过期删除。
- R-B04：真实 recoverable boundary 决定 editable；真实 HTTP/浏览器编辑通过，旧 imported 消息仍禁用整体恢复。
- R-B07：恢复输入前 running_summary、working_records 与 pending_draft，不用全部 UI 历史重造压缩窗口。
- 审批取消/崩溃：applied 同事务设置 approval maintenance，清草稿与 mutation published/解除维护同事务。CancelledError 回归验证启动补完，不重复正文写入，索引一致。
- 目录/附件：目录不加 .md；空目录独立版本；旧/新路径向量均维修；重命名恢复 raw 附件和目录，预览后新增附件整次拒绝。

### 真实演练证据

`test_live_worker_kill_and_restart_preserves_recovery`：worker 保存会话、自有 A 与 Library B，并真实入索引；恢复在 candidate_saved 落库后阻塞，父进程实际 kill；新进程重开同一临时 PG schema/saver/Git/Chroma，确认 durable maintenance 保留，retry 同一任务，再 claim prepared 完成生成，检查 A/向量已删除、B/向量保留、消息/head 一致及维护解除。

`test_two_processes_refuse_chat_write_and_rebuild`：一个 worker 持 exclusive gate，另一进程分别尝试 read/chat/mutate/recovery/model_rebuild 全部快速拒绝；持锁 worker 终止后可重新获取门禁。普通写盘后 Git 前死亡窗口另以 KeyboardInterrupt 回归验证持久阻断与补偿。

`checkpoint-edit-real.spec.ts`：浏览器连接隔离真实 HTTP，编辑真实可恢复消息、显示 A.md 确认弹窗、确认恢复、prepared 生成、刷新保持一次 edited user 和一次重新生成回答，笔记列表无 A。`message-recovery.spec.ts` 新增失败任务刷新仍可重试。

### 追溯与验证边界

上层链路：BIZ→REQ-018→ARC-001/004/005/006、ADR-002→MOD-002/003/004/005/006/008/011→API-001/002/003、DATA-001/002→TC-REQ-018-001→OPS-001/002/003→GOV-002、CR-2026-004。文档保持 review，没有创建 releases 冻结快照。

本轮需求内实现与 G01–G16 补验完成。演练模型/embedding 为确定性替身，持久层/进程/HTTP 为真实实现。Docker Compose 命令在此环境不可用，因此只有 YAML/卷配置静态校验，没有镜像构建/启动；生产模型质量、线上部署和人工发布审批未执行。用户个人参考文档及原 handoff 删除未纳入提交。

## 原 B1–B9 执行记录（补验前）

执行分支：`codex/checkpoint-shadow-git-completion`（自 `main` 的 `333280a` 建立）。
本文件由执行方回填，逐任务记录提交、改动、命令、结果与遗留项；不改写原计划步骤。

## 阶段 A：正式 Agent 状态迁移 —— 已完成

| 任务 | 提交 | 状态 |
|---|---|---|
| A1 旧会话无损导入 | `deab0a7` | 完成 |
| A2 正式聊天／草稿／装配切到图执行 | `730ac9f` | 完成 |
| A3 服务端消息身份、复制 | `fe44f3c` | 完成 |

### A1 `feat(conversations): import legacy histories into checkpoints`

- 改动：新增 `conversations/migration.py`、`scripts/migrate_conversations.py`、
  `tests/integration/test_conversation_migration.py`；`records.py` 增
  `edit_unavailable_reason`；`pyproject.toml` 的 pytest `pythonpath` 增 `.`（导入 CLI）。
- 机制：只读 dry-run 统计 → 每会话写候选 checkpoint（`publish=False`）→ 读回核对消息
  id／正文 → 单事务 CAS 切换 `state_backend` 并建立分支头。失败不删旧表、不发布半成品，
  可按会话重试；已迁移会话重复运行计为 `already_imported`。
- 旧历史无安全边界：导入消息不建 `UserMessageBoundary`，并标注
  `edit_unavailable_reason=history_not_recoverable`，不伪造 `notes_commit`。
- 命令与结果：`.venv\Scripts\python.exe -m pytest tests/integration/test_conversation_migration.py -q`
  → **6 passed**；CLI 两次 apply 对比消息 id 与活动 head 一致。
- 遗留：无。

### A2 `feat(chat): use checkpoint graph in production routes`

- 改动：`chat/agent.py` 重写为图 facade；新增 `chat/session.py`（装配与 seed 辅助）；
  `chat/router.py` 的 `/chat` 改为依赖内 `claim_turn`（先落库用户消息、再 SSE）；
  `bootstrap/app.py`／`runtime.py` 让运行时共享同一 `ConversationService` 与 saver；
  `prompt_eval/run.py`、`rag_eval/agent_run.py` 改走图；`conversations/service.py` 增
  `expected_revision` 与 checkpoint 版 pending_draft 读写；删除过时的
  `tests/unit/test_chat_agent_context.py`。
- 机制：`/chat` 在依赖阶段完成会话解析与用户消息持久化，重复 request_id／busy／
  stale revision 返回真实 409，未知会话返回 404；SSE 复用图事件（token／think／tool／
  sources／answer／draft）。详情、消息、pending_draft 对 checkpoint 会话从活动 head 投影，
  未迁移的 legacy 会话保留旧读路径；草稿编辑／审批经 CAS，且 stale 校验在任何写盘之前。
- 命令与结果：计划指定
  `.venv\Scripts\python.exe -m pytest tests/integration/test_checkpoint_chat_api.py tests/integration/test_checkpoint_draft_api.py tests/unit/test_graph_execution.py tests/integration/test_turn_recovery_pg.py -q`
  → **22 passed**；全量后端 `tests/unit tests/integration` → **559 passed**。
- 遗留：批准草稿仍经旧 `chat/drafts._write_draft` 写盘（B3 换成统一 mutation 服务）；
  未迁移的 legacy 会话在 `/chat` 返回 409，需先跑 A1 导入。

### A3 `feat(chat): expose durable message identities and copy actions`

- 改动：`chat/schemas.py` 的 `MessageOut` 增 `turn_id`／`editable`／`edit_unavailable_reason`；
  `chat/router.py` 统一投影并可标记编辑禁用原因；`PreparedTurn` 增 `request_id` 并在
  `user_message` SSE 回传；前端 `types.ts`、`sse.ts`（解码 `user_message`／`turn_complete`）、
  `api.ts`（带 request_id）、`store.ts`（身份字段与按 request_id 替换乐观行）、新增
  `UserMessageActions.vue` 与 `clipboard.ts`，`MessageList.vue` 挂载复制／编辑入口。
- 机制：复制直接 `navigator.clipboard.writeText` 原文，拒绝或缺失返回可见失败；编辑按钮
  在无安全边界时禁用并回显服务端原因；乐观用户行按幂等键替换为服务端 id，不按文本或下标。
- 命令与结果：`npm run test:unit` → **130 passed**；`npm run test:e2e` → **56 passed**；
  `npm run build` → 通过。后端新增身份／禁用原因断言，全量 **559 passed**。
- 遗留：`editable` 目前恒为 false（B 未完成），符合计划“B 未完成时编辑禁用并给出原因”。

### 阶段 A 覆盖的验收要点（非最终 G 项）

- 正式 HTTP 生成→刷新→重启保留同一状态：`test_checkpoint_chat_api.py::test_restart_preserves_http_history_and_pending_draft`（真实 PostgreSQL + 真实 saver 重开）。
- 压缩不丢 UI 全文：`tests/unit/test_chat_graph.py::test_compaction_keeps_display_history`。
- 草稿恢复：重启用例断言 pending_draft 由 checkpoint 恢复；引用随助手消息持久化。
- 旧消息导入不伪造可编辑资格：A1 `test_imported_history_is_not_falsely_editable`。
- 旧消息表不再承担正式会话状态读写：A2 `test_http_chat_uses_checkpoint_without_legacy_message_writes`（旧写入被 sabotage 仍完成）。

## 阶段 A 验收缺陷修复（回应 review）

依据：[阶段 A 验收记录](2026-10-04-checkpoint-shadow-git-completion-review.md)。修复提交 `c754c66`。

| 编号 | 问题 | 修复 | 测试 |
|---|---|---|---|
| S1 | 草稿变更绕过活动运行 claim | `_publish` 增 `require_no_active_run`：草稿发布在同一事务内检查 prepared/running/interrupted，占用即 `ConversationBusy` | `test_conversation_draft_cas.py::test_draft_edit_refused_while_a_turn_owns_the_conversation` |
| R1 | 草稿 CAS 重新读取 head 造成丢更新 | `_republish_state` 以读取时的 checkpoint id／generation／revision 发布（`write_state(publish=False)` + 显式 `publish_head`），旧 view 被拒绝 | `test_draft_edit_from_a_stale_view_is_rejected`（断言新 summary 保留） |
| R2 | 正式 HTTP 缺少中断续接 | `POST /chat` 支持 `run_id` 续接（不重复接受用户消息）；详情返回 `active_run`；`Agent.resume` 接入 | `test_checkpoint_chat_api.py::test_interrupted_run_resumes_over_http_without_duplicate_user` |
| R3 | generation 被当草稿版本，stale 校验无效 | 新增 `conversations.revision`（Alembic `d4a7e1b90c22`），详情／SSE／草稿保存／审批传真实 revision | `test_checkpoint_draft_api.py::test_stale_tab_approval_is_rejected_with_real_revisions` |

验证：后端 `tests/unit tests/integration` → **563 passed**；前端 `test:unit` **130 passed**、`test:e2e` **56 passed**、`build` 通过；Alembic 在临时 schema 上 upgrade／downgrade／再 upgrade 通过。

已知遗留（未在本次修复，属 B 范围）：批准正文后清 checkpoint 草稿，若 saver／DB 失败则正文已改、索引未更新；B3／B4 的持久 mutation、幂等与索引维修必须覆盖它。

## 阶段 B：笔记、RAG 与整体回退 —— 进行中

| 任务 | 提交 | 状态 |
|---|---|---|
| B1 持久台账与跨进程工作区门禁 | `19b5fdc` | 完成 |
| B2 真实影子 Git 与初始笔记版本 | `9351044` | 完成 |
| B3 统一正式笔记写入 | `a69a082` | 完成 |
| B4 可靠的单文件 RAG 更新与维修 | `1d85826` | 完成 |
| B5 纯预览计划与共享修改冲突 | `2456da1` | 完成 |
| B6 整体恢复状态机 | `0c8b891` | 完成 |
| B7 恢复 API 与 prepared-turn 重推理 | `fbb8c4e` | 完成 |
| B8 编辑、确认弹窗、冲突和进度 UI | `f1a256e` | 完成 |
| B9 真实恢复演练与文档同步 | 本次提交 | 完成（见下） |

### B1 `feat(recovery): add durable workspace gate and journals`

- 改动：新增 `recovery/{__init__,models,schemas,gate}.py`、Alembic `e7b1c2f4a903`；
  `db/__init__.py` 注册模型；`bootstrap/app.py` 构造门禁并注入
  `ModelRuntimeService`；`model_management/service.py` 在重建 worker 内以独占门禁包裹。
- 机制：`workspace_state`（seq／current_commit／maintenance）、`mutation_records`（operation_id 唯一）、
  `recovery_previews`、`recovery_jobs`、`index_repairs`。PostgreSQL 用专用连接的会话级
  advisory lock（read/chat 共享，mutate/recovery/model_rebuild 独占，`pg_try_*` 快速返回）
  加持久 maintenance 行；进程死亡释放锁后 maintenance 仍阻断；SQLite 走进程内读写锁。
- 命令与结果：`pytest tests/integration/test_workspace_gate_pg.py -q` → **6 passed**；
  全量后端 **576 passed**；Alembic 临时 schema upgrade/downgrade/upgrade 通过。
- 遗留：门禁尚未接入 chat/notes 路由的读写门（B3、B6 落地时接入）。

### B2 `feat(notes): persist note versions in isolated shadow git`

- 改动：新增 `notes/versions.py`、`tests/integration/test_notes_versions.py`；
  `settings.py` 增 `NOTES_HISTORY_DIR`（默认 `var/notes_history`，相对项目根）；
  `app.py` 启动时构建并 best-effort 初始化版本仓库（Git 不可用为 None）；
  `.gitignore` 显式忽略 `var/notes_history/`。
- 机制：独立 bare 仓库，`hash-object`/`mktree`/`commit-tree` 全走 argv 且 `shell=False`，
  按原始 bytes 建 blob→tree→commit；`refs/versions/<operation_id>` 保留每个操作提交，
  manifest blob（含空文件夹）经 `refs/manifests/<commit>` 读取；无差异复用父提交；
  路径／提交校验拒绝 `..`、绝对路径、非 40-hex 提交与隐藏路径；symlink 不跟踪。
- 命令与结果：`pytest tests/integration/test_notes_versions.py -q` → **7 passed, 1 skipped**
  （symlink 用例在无权限平台跳过）；全量后端 **583 passed, 1 skipped**。
- 遗留：`snapshot/read_blob` 已具备，尚未被写入路径调用（B3 接入）。

### B3 `feat(notes): route all durable writes through mutation service`

- 改动：新增 `notes/mutations.py`、`tests/integration/test_notes_mutations.py`；
  `notes/repository.py` 增 `path_of`；`notes/router.py` 七个写端点改走 `apply`；
  `chat/agent.py` 的 checkpoint 草稿批准改走 `apply`（`_write_approved`）；
  `chat/session.py`、`bootstrap/runtime.py`、`bootstrap/app.py` 注入 mutation 服务。
- 机制：`apply` 先写台账（operation + before blobs），再写盘、提交影子版本、推进
  workspace_seq，最后才报成功；`operation_id` 幂等；`expected_hashes` 不符即 `ConflictError`；
  Git 失败回滚 before bytes 并记 failed；Git 已提交但台账缺失时按保留 ref 续办且不重写磁盘。
- 命令与结果：`pytest tests/integration/test_notes_mutations.py tests/integration/test_checkpoint_draft_api.py tests/integration/test_notes_api.py -q` → **21 passed**；全量后端 **590 passed, 1 skipped**。
- repository 写入调用点审计：`notes/mutations.py`（唯一正式路径）、`notes/router.py` 与
  `chat/drafts.py` 仅剩「无影子仓库」兼容分支（legacy 会话／测试容器）、
  `prompt_eval/run.py::seed_notes`（评测播种）。生产容器始终带 mutation 服务，无生产旁路。
- 遗留：草稿批准的 workspaces gate 顺序（gate→conversation lock）与恢复协调的严格定序在 B6 统一；
  索引仍为 best-effort，B4 换成持久维修记录。

### B4 `fix(retrieval): repair per-file indexes and fence stale chunks`

- 改动：新增 `retrieval/repairs.py`、`tests/integration/test_index_repairs.py`；
  `notes/mutations.py` 的 `_sync_index` 在具备 repairs 时改为「pending→写→验证→ready」并只修受影响路径；
  `bootstrap/app.py` 构建 `IndexRepairService` 注入 mutation 服务。
- 机制：bodies hash 规则 `raw-bytes-sha256-v1`，向量文本规则 `chunk-content-v1`；写入前持久标
  `pending`，全部写完并校验（body hash + config fingerprint + 是否 indexed／空文档零 chunk）才
  `ready`；失败保留可重试任务；`search_synced` 过滤未同步文件的命中；`reconcile` 跨重启重试。
- 命令与结果：`pytest tests/integration/test_index_repairs.py tests/integration/test_retrieval_service.py tests/integration/test_notes_mutations.py -q` → **30 passed**；全量后端 **597 passed, 1 skipped**。
- 遗留：启动时不自动 reconcile（B7 提供显式修复入口）。

### B5 `feat(recovery): preview owned changes and reject shared conflicts`

- 改动：新增 `recovery/planner.py`（纯函数）、`tests/unit/test_recovery_planner.py`。
- 机制：`plan()` 按 workspace_seq 逆序反转本会话 owned mutations 求目标文件／目录状态；他人后续
  操作（含 ABA 写回）、移动交叉、恢复目录内未追踪内容即冲突，`can_apply=False`；无正式写入允许
  仅状态恢复；导入历史 `history_not_recoverable`。`RestorePlan` 记录 state_revision／workspace_seq／
  target hash／content digest／expires_at，preview 不触碰正文／索引／活动 head。
- 命令与结果：`pytest tests/unit/test_recovery_planner.py -q` → **7 passed**；全量后端 **604 passed, 1 skipped**。
- 遗留：`recovery/schemas.py` 的 API 出参模型在 B7 一并落地。

### B6 `feat(recovery): coordinate durable file index and state restoration`

- 改动：新增 `recovery/service.py`、`tests/integration/test_recovery_coordinator.py`；
  `notes/mutations.py` 增 `restore()`（原始 bytes 补偿提交）；`conversations/service.py` 增
  `fork_for_edit`／`publish_recovery`／`claim_prepared` 与 `workspace_seq_provider`；
  `recovery/gate.py` 增 owner 绕过（任务可进入自己的 maintenance）；`bootstrap/app.py` 注入协调器。
- 机制：`prepared→restoring_files→reindexing→preparing_state→publishing→succeeded` 逐阶段持久化；
  候选 checkpoint 先写不可见，publish 在同一 DB 事务内 CAS 切分支／head／generation、发布 job 成功
  与 prepared_turn_id、清 maintenance；失败保留 failed+maintenance，retry 续办同计划。
- 命令与结果：`pytest tests/integration/test_recovery_coordinator.py tests/integration/test_turn_recovery_pg.py -q` → **10 passed**；全量后端 **608 passed, 1 skipped**。

### B7 `feat(api): expose recovery jobs and prepared turn execution`

- 改动：新增 `recovery/router.py`、`tests/integration/test_recovery_api.py`；`recovery/schemas.py`
  出参模型；`chat/{router,schemas,agent}.py` 支持 `prepared_turn_id`；详情返回 `recovery`；app 注册
  路由与 `RecoveryError` 处理。
- 机制：`POST …/recoveries/preview`、`POST …/recoveries`、`GET /recoveries/{id}`、
  `POST /recoveries/{id}/retry`；统一 code/message/retryable；缺确认→409 confirmation_required、
  冲突→409 conflict、过期→409 preview_expired；`prepared_turn_id` 唯一认领已接受消息。
- 命令与结果：`pytest tests/integration/test_recovery_api.py tests/integration/test_checkpoint_chat_api.py -q` → **13 passed**；全量后端 **611 passed, 1 skipped**。

### B8 `feat(frontend): edit messages through confirmed recovery jobs`

- 改动：新增 `MessageEditForm.vue`、`RecoveryConfirmDialog.vue`、`recovery.ts` 与前后端测试；
  `MessageList.vue`、`store.ts`、`api.ts`、`types.ts`。
- 机制：Enter 换行／Ctrl·⌘+Enter 提交／Esc 取消／IME 不提交；预览→确认弹窗（文件＋目录清单、
  冲突只可取消）→轮询真实任务→成功后重载活动状态与 Library 并用 prepared_turn_id 续接，不重复
  接受用户消息；轮询失败可重试。
- 命令与结果：`npm run test:unit` → **139 passed**；`npm run test:e2e` → **59 passed**；`npm run build` 通过。

### B9 演练与文档同步

- 新增 `tests/integration/test_full_rollback_acceptance.py`：G08（仅回退 owned 文件、保留他会话文件、
  只修 A 索引、head 与 notes_commit 一致、编辑消息只接受一次）、G11（无正式写入→仅状态恢复、无
  无意义 commit）、G09（共享修改整次拦截且正文不变）、G13（重复 start 返回同一 job）。
- 部署持久化：`NOTES_HISTORY_DIR` 默认 `var/notes_history` 且不得位于 `notes_dir` 内（`NoteVersionStore`
  构造即拒绝嵌套）；notes／chroma／postgres 均按配置持久化路径。**未做长驻服务的真停／重启演练**
  （本环境无长驻进程）；重启一致性由真实 PostgreSQL saver 重开用例与协调器用例覆盖。
- 文档同步：本结果文件与计划索引已更新；上层 NoteAgent-docs 未在本轮本地同步（属独立版本仓库，
  待用户指令）。

## 最终验收门槛 G01—G16 状态

| ID | 场景 | 状态 | 证据 |
|---|---|---|---|
| G01 | 正式聊天不写旧表，刷新／重启同状态 | 通过 | `test_checkpoint_chat_api.py`（含真实 PG 重开） |
| G02 | 压缩不丢全文；重复导入无重复；不可恢复历史禁用 | 通过 | `test_chat_graph.py`、`test_conversation_migration.py` |
| G03 | 并发发送／断开／续接／模型切换 | 通过 | `test_graph_execution.py`、`test_checkpoint_chat_api.py` |
| G04 | 普通聊天无笔记 commit；正式写入有完整版本 | 通过 | `test_notes_mutations.py`、A2 用例 |
| G05 | Library／草稿写入无旁路 | 通过 | `test_notes_mutations.py`＋router 走 mutation |
| G06 | 单文件增改删移只动受影响路径 | 通过 | `test_index_repairs.py`、`test_notes_mutations.py` |
| G07 | 索引失败可重启修复，不返陈旧 | 通过 | `test_index_repairs.py` |
| G08 | 编辑仅回退本会话 A，B 不变，仅更新 A 索引 | 通过 | `test_full_rollback_acceptance.py::test_g08_...` |
| G09 | 他会话／Library／external 改 A 整次拦截 | 通过 | `test_recovery_planner.py`、`test_full_rollback_acceptance.py` |
| G10 | 文件／目录变化确认与取消；绕过确认被拒 | 通过 | `test_recovery_api.py`、`tests/e2e/message-recovery.spec.ts` |
| G11 | 无文件改动的历史编辑仍恢复状态并重新生成 | 通过 | `test_full_rollback_acceptance.py::test_g11_...` |
| G12 | 分阶段故障、真实进程终止重启、维护阻断、续办 | 通过 | live worker kill/restart + coordinator fault-stage + cancelled approval 回归 |
| G13 | 发布后重复 start／prepared-turn 同一结果 | 通过 | `test_full_rollback_acceptance.py::test_g13_...`、`test_recovery_api.py` |
| G14 | 双 worker、恢复/模型重建互斥 | 通过 | test_recovery_process_drills.py 的 two-process contention；writing maintenance 崩溃回归 |
| G15 | 复制／编辑／弹窗／旧 SSE 隔离 | 通过 | `tests/e2e/checkpoint-chat.spec.ts`、`message-recovery.spec.ts`、单测 |
| G16 | 持久卷/备份、双仓文档追溯 | 通过（Docker 未运行） | Git/持久 history 卷静态检查；真实 PG/Git/Chroma 重启；上层仓库 eb59aa5 与 CR-2026-004 |

未达标项集中在需要长驻服务／双进程／上层仓库的 G12、G14、G16 的“真实演练”部分；功能与持久化
代码路径均由测试覆盖，但按计划口径不作为“整体完成”宣布。

以上原执行中 G12/G14/G16 的未完成说明是补验前记录；最新结论以本文顶部为准。Docker 构建/运行尚未执行。

## 现场验收补修：历史迁移与消息编辑权限（2026-10-04）

- 本地启动只完成数据库结构升级，旧会话未导入 checkpoint。迁移 dry-run 与 apply 导入 5 个会话、77 条内部消息，另 1 个会话已使用 checkpoint，无失败。确认全部 6 个会话使用 checkpoint，导入会话的 30 条用户/助手展示消息 ID 与正文与旧数据一致；旧表保留。
- 导入的旧用户消息缺少当时的文件恢复边界，返回 history_not_recoverable，仍禁止编辑回退。新消息保存恢复边界后可编辑。
- 前端乐观消息默认 editable=false，流式回复完成后未同步服务器编辑权限，导致新消息需刷新才可编辑。现改为流式执行结束后按消息 ID 同步服务器权限与禁用原因，并校验当前会话和选择版本，避免串会话覆盖。
- 前端 143 单测、62 个端到端测试、构建全部通过。新增真实 HTTP 浏览器测试覆盖“新消息发送完成后无需刷新即可编辑”，原真实编辑回退测试继续通过。本地服务已提供新版构建资源。

## 现场验收补修：编辑确认与笔记/RAG 回退（2026-10-04）

- 根因：submitEdit 根据 requires_confirmation=false 自动 confirmRecovery，纯状态回退导致确认弹窗闪过且未等待用户确认。所有可执行编辑预览现统一进入 confirming，只有该阶段的明确确认才能 start；冲突仍不可强制应用。
- TDD：新增纯状态预览不发送、不修改消息用例，修复前失败（running 而非 confirming）；修复后通过。浏览器验证 Ctrl+Enter 提交后保持确认弹窗，取消不调用恢复或 chat。
- 真实 HTTP 浏览器验收增强：隔离服务使用真实影子 Git 与 Chroma，A.md 是会话新增，B.md 是之后的 Library 新增；预览前后 revision、用户消息与两份分块完全相同；确认后 A.md 及其分块移除，B.md 及分块保留，修改后用户消息与重新生成回答刷新后持久存在。模型与 embedding 为确定性替身。
- 验证：144 前端单测、63 个端到端、构建通过；后端 test_full_rollback_acceptance.py 4 passed。初次新增浏览器用例的文案选择器错误已修正，重跑完整套件通过。本地 8000 服务提供新版前端资源。
- 顺序：确认前只预览；确认后先恢复材料并验证索引，发布活动 checkpoint 与 prepared turn，随后发送 prepared turn 重新推理。上层 REQ-018/ARC-004/MOD-008/TC-REQ-018-001 同步统一确认约束。

## 现场验收补修：消息原位编辑（2026-10-04）

- 编辑表单移动到原用户消息气泡内，与静态正文互斥渲染；编辑时隐藏复制/编辑动作，取消后恢复原正文与动作，避免一条消息显示两份内容。
- 操作区支持自动换行，窄屏按钮与快捷键提示不会挤在同一行。
- 验证：构建通过，消息编辑/确认/冲突与复制的 6 个浏览器测试通过；断言编辑时原 msg-body 不存在、气泡内只有一个 textarea，取消后正文恢复。

## 现场验收补修：长消息编辑保持全文展开（2026-10-04）

- 编辑区沿用消息气泡字体、行高、背景与正文位置，移除第二层边框和额外内边距；高度按全文自动展开，隐藏内部滚动条，内容修改与视口宽度变化后重新测量。
- 新增 100 行真实浏览器显示回归：修复前编辑框仅 91px，而正文约 2379px，用例失败；修复后编辑高度覆盖全文，新增行及窄屏切换均无内部溢出，取消恢复原正文。
- 验证：构建与 7 个相关浏览器测试通过。本地服务已提供新版资源。

## 现场验收调整：顶部草稿更名与底部直接追加（2026-10-04）

- 新建草稿点击顶部笔记名进入编辑，Enter/失焦确认本地名字，Esc 取消。保存草稿及审批前自动保存将正文和目标名一起写入 checkpoint，刷新后保留，审批前不写 notes 或索引。
- PUT /chat/draft 增加可选 file_name，仅 create 草稿可更名；沿用笔记路径规范化、revision CAS、运行占用拒绝。非法路径返回 422，过期版本返回 409，批准后才创建新名字的文件。
- DraftActions 删除更多操作菜单及底部新建名字表单，底部直接展示同意/拒绝/追加到笔记。追加展开目标选择与独立确认；无目标时禁用确认。
- 测试先复现后端忽略 file_name 的失败，再验证更名持久、非法路径不改草稿、过期版本拒绝、批准仅写入新名。浏览器覆盖顶部更名/取消/保存后刷新、直接选择追加目标及审批/拒绝原有流程。
- 验证：后端 tests/unit tests/integration 647 passed, 1 skipped；前端 144 单测、64 端到端与 build 通过。重启本地服务后核验 8000 页面为新构建、OpenAPI 含草稿 file_name 字段。
- 上层 MOD-008 与 API-002 同步更新交互和接口约束。

## 合并前审查补修：草稿保存期间的更名竞态（2026-10-04）

- 独立审查复现延迟草稿保存返回后覆盖更新文件名的竞态。保存期间锁住面板编辑和用户保存入口（包括 Ctrl/Cmd+S），结束时恢复原 busy 状态，保留审批拥有的锁。
- 回归用例先失败、修复后通过；145 前端单测、8 个草稿面板端到端及构建通过。此前完整回归为后端 647 passed/1 skipped、前端 64 e2e；此次只修改前端保存锁。
