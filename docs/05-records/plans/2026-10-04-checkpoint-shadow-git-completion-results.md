# Checkpoint、影子 Git 与 RAG 整体回退修复／完成计划 —— 执行结果

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

## 阶段 B：笔记、RAG 与整体回退 —— 待执行

B1—B9 未开始。以下范围与计划一致，尚无实现、无测试、无提交：

- B1 持久台账与跨进程工作区门禁（`recovery/` 基础 + Alembic revision + advisory lock）。
- B2 真实影子 Git 与初始笔记版本（`notes/versions.py`、`NOTES_HISTORY_DIR`）。
- B3 所有正式笔记写入归一并关联 checkpoint（`notes/mutations.py`）。
- B4 可靠的单文件 RAG 更新与维修（`retrieval/repairs.py`）。
- B5 纯预览计划与共享修改冲突（`recovery/planner.py`）。
- B6 整体恢复状态机、幂等重启和最后发布（`recovery/service.py`）。
- B7 恢复 API 与 prepared-turn 重推理（`recovery/router.py`）。
- B8 用户消息编辑、确认弹窗、冲突和进度 UI。
- B9 真实恢复演练、部署持久化及文档同步 + G01—G16 逐条证据。

因此当前**不能视为整体迁移完成**：编辑入口保持禁用，未对任何用户 notes 做回撤。
后续按 A→B 顺序续做，合并／推送作为后续用户指令执行。
