# Checkpoint、影子 Git 与 RAG 整体回退修复／完成计划

> **For agentic workers / Qoder:** 按任务顺序执行，每项先补失败测试，再实现并提交验证证据。若安装了 executing-plans 技能，可使用该技能逐项执行。本计划是原计划的剩余工作执行入口，不能以新增类、模拟接口、旧测试通过代替正式业务链路验收。

**Goal:** 正式聊天通过持久化 checkpoint 保存和读取 Agent 状态；所有正式笔记变更进入影子 Git；普通写入与历史消息编辑回退均可靠更新受影响文件的 RAG 索引。

**Architecture:** 复用已实现的 ConversationService、图节点、执行租约和 CAS 发布逻辑。分 A（正式会话迁移）和 B（笔记版本、索引修复、整体恢复及编辑 UI）两阶段推进，模块接口和恢复规则沿用已确认的上层设计。

**Tech Stack:** 当前锁定的 Python、FastAPI、SQLAlchemy/Alembic、LangGraph/AsyncPostgresSaver、PostgreSQL、Git、Chroma、Vue/Pinia、Vitest、Playwright；不为本轮迁移无关升级依赖。

**Spec / 需求与设计依据：**

- [原始实施计划](2026-10-01-checkpoint-shadow-git-rollback.md)：尤其 §1、§4—6 的状态、门禁、幂等及 API 合同；本计划不取消其任何验收要求。
- [已有执行结果](2026-10-01-checkpoint-shadow-git-rollback-results.md)、[验收记录](2026-10-02-checkpoint-shadow-git-rollback-review.md)、[已修复与剩余范围](2026-10-02-checkpoint-shadow-git-rollback-fixes.md)。
- [REQ-018](../../../../NoteAgent-docs/docs/02-requirements/REQ-018-历史消息编辑与整体回退.md)、[ADR-002](../../../../NoteAgent-docs/docs/03-architecture/ADR/ADR-002-checkpoint与影子Git协同回退.md)。
- [DATA-001](../../../../NoteAgent-docs/docs/06-data/DATA-001-状态与材料版本关系.md)、[API-001](../../../../NoteAgent-docs/docs/05-interfaces/API-001-会话恢复接口约束.md)、[TC-REQ-018-001](../../../../NoteAgent-docs/docs/07-quality/TC-REQ-018-001-回退验收场景.md)。
- 上层模块：MOD-002 会话、MOD-003 Agent、MOD-004 笔记版本、MOD-005 检索、MOD-006 恢复、MOD-008 前端、MOD-011 装配与部署。

**执行状态：** 待执行。2026-10-04 基于 `main` 的 `333280a` 核对；本次仅制定计划，没有实施下列任务，也没有重新运行功能测试。

## 1. 当前事实与执行边界

| 能力 | 已有事实 | 必须补齐 |
|---|---|---|
| checkpoint | PostgreSQL saver、GraphState、图节点、prepare/execute、执行租约、CAS、基础恢复测试已存在 | 正式 ChatAgent、HTTP、模型切换装配、评测脚本和草稿处理切换；旧会话导入 |
| 影子 Git | 只有目标设计，尚无正式版本服务 | 初始版本、变更归属、目录 manifest、统一正式写入、版本持久化及修复 |
| RAG | notes/router.py 与 chat/drafts.py 在写入后尝试更新，失败主要记录日志 | 正文哈希与配置指纹验证、持久化修复任务、禁止陈旧检索、回退时按文件更新 |
| 编辑／复制 | 未完成新合同及 UI | 服务端消息 ID、复制、编辑预览、文件确认弹窗、冲突拦截、任务查询与重推理 |

2026-10-02 的 552 项测试是已有实现范围的回归证据，不是本计划的完成证据。原计划 Task 0—1 及 Task 2 的基础部分不重写，先保留其测试；本轮完成原 Task 2—12 的剩余工作。

1. 执行从新分支 `codex/checkpoint-shadow-git-completion` 开始；不直接在 main 开发。每任务只提交明确列出的变更，不使用 `git add -A` 混入个人笔记。
2. 保护现有 `docs/references/思考.md`、未跟踪的个人参考文件和 `docs/roadmap/`。测试使用临时数据库 schema、笔记目录、影子仓库与 Chroma，不恢复或改写真实用户笔记。
3. 编辑第 N 条用户消息，恢复到接收该消息之前的安全边界，创建新活动分支，再接收修改后的消息一次。原分支、原消息和旧 checkpoint 保留。
4. UI 全量历史与模型压缩上下文分开；摘要不得删除 UI 原文。引用、工具步骤、草稿、压缩水位和稳定消息 ID 必须持久化。
5. 只撤销当前会话活动历史在边界之后实际执行的正式笔记操作。其他会话、Library、外部编辑的后续改动冲突时整次拦截，保留全部后续更改，无强制覆盖入口。
6. 任意正式文件／文件夹变更都要在预览中列出并弹窗确认；取消不改变正文、向量、消息及活动指针。没有文件变化仍走服务端预览和恢复流程。
7. 默认 `NOTES_HISTORY_DIR=var/notes_history`，相对项目根目录解析，可配置为绝对路径；与 notes_dir、代码仓库 .git 隔离并持久化。普通聊天、摘要或草稿编辑不生成笔记 commit。
8. checkpoint 携带 `notes_commit` 与 `workspace_seq`，无正文变化可共享 commit；不得给每条消息强行制造新 commit。恢复后的 checkpoint 指向补偿后的全工作区版本。
9. 文件系统、Git、Chroma 和 checkpoint 无共同事务，必须使用持久任务、幂等步骤、维修状态和最终 CAS 发布。不得以一串 try/except 顺序调用假装原子性。
10. Git bytes、正文 bytes、目录结构按原样恢复。禁止全局 reset/clean、删除 messages 后重发、仅修改前端消息列表、以 saver 最新位置代替活动 head。
11. A 可独立验收；B 全部必过项完成后才能启用历史编辑。复制无需等待 B。

## 2. 文件分区与接口

所有源码路径均相对 `src/noteagent/`；前端相对 `frontend/`。新文件在首次实现对应任务时创建，避免空壳接口或平行的旧／新 Agent 长期共存。

| 分区 | 文件 | 职责 |
|---|---|---|
| conversations | 复用 records.py、contracts.py、models.py、checkpoints.py、leases.py、service.py；新增 migration.py | 状态投影、导入、活动分支、消息边界、候选 checkpoint 与发布；不直接调 Git/Chroma |
| chat | 修改 agent.py、router.py、schemas.py、drafts.py、tools.py；复用 graph.py、nodes.py、events.py、execution.py | Agent facade、图执行、SSE 映射、草稿状态；正式写入交给 NotesMutationService |
| notes | 复用 repository.py；新增 versions.py、mutations.py；修改 router.py | 路径安全与底层 IO、Git bytes、正式写入编排 |
| retrieval | 修改 service.py、vector_store.py、models.py；新增 repairs.py | 单文件分块／向量一致性与可重试修复；不决定活动会话 head |
| recovery | 新增 __init__.py、models.py、schemas.py、gate.py、planner.py、service.py、router.py | 工作区门禁、变更／恢复台账、纯预览计划、恢复状态机和 HTTP 映射 |
| bootstrap | 修改 app.py、runtime.py、settings.py | saver 生命周期及模块注入；模型切换后的 runtime 仍使用同一会话服务 |
| frontend/src/features/chat | 新增 UserMessageActions.vue、MessageEditForm.vue、RecoveryConfirmDialog.vue、recovery.ts；修改 MessageList.vue、store.ts、api.ts、sse.ts | 按稳定身份编辑／复制，预览与任务状态、旧响应隔离；不包含 Git 实现知识 |

**复用的真实接口：** `ConversationService.get_state()`、`list_messages()`、`prepare_turn(conversation_id, question, request_id)`、`resume_turn(run_id)`、`record_run_checkpoint()`、`finish_run()`；`execute_turn(graph, service, prepared, resume=False)`；`build_chat_graph(runtime, checkpointer)`。保留 PreparedTurn 的 accepted head、运行位置及 lease token 语义；涉及 expected_revision 的扩展放在同一服务中验证。

**本轮新接口：** 沿用原计划 §4.3 定义，具体输入输出 dataclass/Pydantic 类型在首次实现时集中定义，后续任务直接导入：

```python
# notes/versions.py
snapshot(parent_commit, operation_id)  # -> commit + changed paths；无变化复用 commit
read_blob(commit, path)                # -> bytes | None
# notes/mutations.py
async def apply(command, origin, operation_id, expected_hashes): ...
# recovery/gate.py
operation(mode)  # async context manager: read/chat/mutate/recovery/model_rebuild
# recovery/planner.py
plan(boundary, owned_mutations, later_mutations, current_manifest)  # -> RestorePlan
# recovery/service.py
async def preview(conversation_id, message_id, edited_content, expected_revision): ...
async def start(preview_id, edited_content, confirmed_file_changes, operation_id): ...
async def retry(job_id, operation_id): ...
# conversations/service.py
async def fork_for_edit(job): ...       # 幂等准备未发布候选状态及 prepared turn
async def publish_recovery(job): ...    # DB 事务内发布分支/head/任务成功
```

以上是接口签名说明，不是可直接替代实现的代码。Origin、MutationResult、RestorePlan、PreviewOut、JobOut 的字段必须覆盖原计划 §4 和 API-001；不能改名后造成前后端合同分歧。恢复任务记录真实的候选配置，不通过“最新 checkpoint”找回它。

## 3. 测试与结果记录约定

新增 `tests/support/rollback.py`、必要的 `tests/support/__init__.py` 与 conftest fixtures：

- `checkpoint_app`：通过真实 FastAPI lifespan 打开 saver，使用确定性 FakeChatModel；提供 client、service、数据库 session_factory，并能关闭重开。
- `recovery_harness`：真实临时 bare Git、笔记仓库、Chroma、确定性 Embedder、真实服务与临时 PostgreSQL schema；只在外部 LLM 和故障点注入替身。
- helper 按原计划 Task 0 合同提供 `create_conversation`、`complete_turn`、`conversation_with_approved_change`、`get_state/get_job` 及阶段故障注入；不 mock 掉被验收的恢复协调器。
- 为每个故障点记录调用次数和实际正文／向量／DB/head；测试不能只断言 HTTP 200 或 mock 被调用。

新增执行结果文件 `2026-10-04-checkpoint-shadow-git-completion-results.md`，逐任务记录：提交 SHA、改动、实际命令、结果、失败／未执行项、证据路径。最终增加 G01—G16 的逐条证据。未运行、环境不足、skip 均不能标成通过。

每任务循环为：添加下述失败测试 → 运行指定文件确认业务断言失败 → 实现 → 重跑通过 → 显式暂存该任务文件并提交 → 回填证据。新测试文件名与下面命令一致，不要仅新增测试说明。

## 4. 阶段 A：正式 Agent 状态迁移

### A1：旧会话无损导入与明确恢复边界（原 Task 3 的导入部分）

**Files:** 新增 conversations/migration.py、scripts/migrate_conversations.py、tests/integration/test_conversation_migration.py；修改 conversations/service.py、records.py、models.py，必要时新增 Alembic revision。

- [ ] 添加 `test_import_preserves_messages_summary_draft_and_citations`、`test_import_retry_does_not_duplicate_messages`、`test_imported_history_is_not_falsely_editable`，覆盖工具步骤、原 ID／时间、摘要水位及草稿。
- [ ] 先实现只读 dry-run，统计会话／消息数、不可识别状态及错误；导入采用候选 checkpoint→数据核对→CAS 切换 backend。失败不删除旧表、不发布半成品，可按会话重试。
- [ ] 不可重建的旧历史标记 `history_not_recoverable`。导入时无法知道旧笔记版本，不伪造历史 notes_commit；B 初始化后，只为之后真正建立的安全边界开放编辑。
- [ ] CLI 定义 `--dry-run`、`--apply`、可选 `--conversation-id`，输出计数和错误，不输出消息原文或连接凭据。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_conversation_migration.py -q`。在临时 schema 运行 CLI 两次，对比消息 ID／内容及活动 head。提交 `feat(conversations): import legacy histories into checkpoints`。

### A2：正式聊天、草稿与装配全部切到图执行（原 Task 2—3）

**Files:** 修改 chat/agent.py、router.py、schemas.py、drafts.py、bootstrap/app.py、runtime.py、model_management 中实际装配调用点、scripts/eval_rag_agent.py 及仍构造旧 Agent 的评测入口；新增 tests/integration/test_checkpoint_chat_api.py、tests/integration/test_checkpoint_draft_api.py。

- [ ] 添加 `test_http_chat_uses_checkpoint_without_legacy_message_writes`：让旧 ConversationStore.append_message 在调用时抛错；请求正式 `/chat`，验证仍完成，并从 checkpoint 读到用户／助手消息和摘要、草稿、引用。
- [ ] 添加 `test_restart_preserves_http_history_and_pending_draft`、`test_duplicate_request_accepts_one_user_message`、`test_switch_model_keeps_same_checkpoint_service`、`test_draft_edit_is_checkpointed_and_stale_review_is_rejected`。
- [ ] Agent 改为图 facade，复用 prepare_turn→execute_turn。正式请求增加 request_id、expected_revision；用户持久化后才发 user_message，完成 durable head 发布后才发 turn_complete。保留既有 token／工具／来源事件展示。
- [ ] 活动会话详情、消息列表、pending_draft 均从活动 head 投影；元数据列表／标题／软删除仍可用应用表。草稿编辑、拒绝、批准状态经过 CAS 保存；批准正式正文暂使用可替换的写入依赖，B3 切入统一服务。
- [ ] SSE 断开等待图清理后释放 claim；重连按明确 run_id 恢复，不重复接受消息。保留现有租约、过期 reconciliation 和候选隔离，不回退到按 thread 最新 checkpoint 查询。
- [ ] 从运行装配、模型切换和评测入口移除旧执行循环使用；legacy store 只供 A1 导入。记录所有 ChatAgent／ConversationStore 构造调用的检索结果。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_checkpoint_chat_api.py tests/integration/test_checkpoint_draft_api.py tests/unit/test_graph_execution.py tests/integration/test_turn_recovery_pg.py -q`。提交 `feat(chat): use checkpoint graph in production routes`。

### A3：服务端消息身份、复制及 A 阶段验收（原 Task 4）

**Files:** 修改 chat/schemas.py、frontend/src/features/chat/api.ts、store.ts、sse.ts、MessageList.vue；新增 UserMessageActions.vue、frontend/tests/unit/user-message-actions.spec.ts、frontend/tests/e2e/checkpoint-chat.spec.ts。

- [ ] 前后端传递 message_id／turn_id／branch_id／generation／state_revision，消息列表返回 editable／edit_unavailable_reason。乐观行通过 request_id 替换成服务端 ID，不能按文本或列表下标匹配。
- [ ] 复制按钮直接点击调用 `navigator.clipboard.writeText(message.content)`，保留原始 Markdown／换行；Promise 拒绝时显示失败，可键盘操作且有 aria-label。
- [ ] 测试相同文本的两条消息身份不同、刷新后 ID 稳定、复制成功／拒绝／无 API。B 未完成时编辑禁用并给出原因，不提供删后续消息的临时方案。
- [ ] 在 frontend 运行 `npm run test:unit -- tests/unit/user-message-actions.spec.ts`、`npm run test:e2e -- tests/e2e/checkpoint-chat.spec.ts`、`npm run build`。
- [ ] A 通过条件：正式 HTTP 生成→刷新→重启均保留同一状态；压缩不丢 UI 全文；草稿／引用恢复；旧消息导入不伪造可编辑资格；旧消息表不再承担正式会话状态读写。提交 `feat(chat): expose durable message identities and copy actions`。

## 5. 阶段 B：笔记、RAG 与整体回退

### B1：持久台账与跨进程工作区门禁（原 Task 6 的基础）

**Files:** 新增 recovery/__init__.py、models.py、schemas.py、gate.py、新 Alembic revision、tests/integration/test_workspace_gate_pg.py；修改 alembic/env.py、bootstrap/app.py、model_management 的索引重建入口。

- [ ] 建立 workspace 状态／seq／current_commit／maintenance_job_id，mutation 台账，preview／recovery job，以及逐路径 index repair 记录；原计划 §4 字段、operation_id 唯一约束、执行租约与候选配置必须落库。
- [ ] 采用 PostgreSQL 专用连接的 session advisory shared/exclusive lock，固定顺序 WorkspaceGate→模型 runtime 租约→会话 CAS→checkpoint IO；不能拿着 runtime Lock 等工作区门禁。
- [ ] read/chat 共享，mutate/recovery/model_rebuild 独占。恢复失败持久 maintenance 状态，即使进程死亡释放锁，正文读取、聊天、写入仍被拒绝；任务查询和修复入口可用。
- [ ] 测试两个真实数据库连接／进程互斥、有效锁不被另一 worker 清除、连接断开释放锁但 maintenance 仍阻断、busy 快速返回、模型重建与恢复不能并行。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_workspace_gate_pg.py -q`，临时 schema 运行 Alembic 升级与重复启动。提交 `feat(recovery): add durable workspace gate and journals`。

### B2：真实影子 Git 与初始笔记版本（原 Task 5）

**Files:** 新增 notes/versions.py、tests/integration/test_notes_versions.py；修改 bootstrap/settings.py、app.py、.gitignore。

- [ ] 独立 bare Git＋临时 index，argv／shell=False，以原始 bytes 的 blob 构造 tree/commit，目录 manifest 存在私有版本结构中；operation_id 对应保留 ref，支持 Git 已提交但 DB 未绑定后的找回。
- [ ] 初始化只读取笔记创建初始版本，不给 notes 写 .git，不改变代码仓库 HEAD/index，不改正文；无差异复用 commit。路径／commit 校验不允许用户输入成为任意 Git ref；拒绝越界 symlink/junction。
- [ ] 测试 CRLF／中文／空文件／空文件夹、移动和删除、同 operation_id 重试、无变化无新 commit、代码仓库不受影响、仓库关闭重开仍可 read_blob。
- [ ] 当前磁盘与已记录版本不一致时，登记 external 来源变更并更新 seq／修复记录；不能把外部修改归到本次聊天。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_notes_versions.py -q`。提交 `feat(notes): persist note versions in isolated shadow git`。

### B3：所有正式笔记写入归一并关联 checkpoint（原 Task 6）

**Files:** 新增 notes/mutations.py、tests/integration/test_notes_mutations.py；修改 notes/router.py、chat/drafts.py、tools.py、bootstrap/app.py、runtime.py、conversations/service.py。

- [ ] 正式 create/write/append/replace/delete/move/folder 操作、Library、草稿批准及实际导入入口全部调用 apply；repository 保留底层 IO，正式 handler 不直接写盘。以代码检索核对所有 repository 写方法调用点。
- [ ] Origin 包含 conversation/branch/run 或 library/external；批准旧草稿按真正执行 seq 归属。校验 draft_id、generation、预览基准哈希；先记录 operation 与可恢复 before blobs，再写盘、commit、repair，不能先 pop 草稿。
- [ ] 一次 create＋正文是一个逻辑操作。预期哈希不一致拒绝；重复 operation_id 返回原结果且不再次 append。Git 失败恢复 before 或进入 repair_required，不返回普通成功。
- [ ] notes_commit／workspace_seq 与 accepted checkpoint 正确关联；Git 成功而 DB／草稿保存失败时从 ref 和台账续办，不重复写盘，待办期间阻断下一次冲突操作。
- [ ] 测试 Library 创建／修改／删除／移动／文件夹、草稿批准／重复／过期批准、写后 Git 失败、Git 后 DB 失败重启恢复、外部修改归属。索引故障在 B4 完成其一致性断言。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_notes_mutations.py tests/integration/test_checkpoint_draft_api.py tests/integration/test_notes_api.py -q`。提交 `feat(notes): route all durable writes through mutation service`。

### B4：可靠的单文件 RAG 更新和维修（原 Task 8 的索引部分）

**Files:** 新增 retrieval/repairs.py、tests/integration/test_index_repairs.py；修改 retrieval/service.py、vector_store.py、models.py、notes/mutations.py、bootstrap/app.py。

- [ ] 索引台账保存正文 bytes hash、索引配置 fingerprint、状态和操作身份；chunk 元数据能关联同一正文版本。index_note 重建前后验证，没有旧 chunk 残留；delete_note 验证零向量；移动处理旧、新路径。
- [ ] 空文档合法零 chunk，用台账匹配 hash/fingerprint 证明同步，不用 is_indexed=true 作为唯一标准。正文 hash 与向量有效文本生成的规则分别明确。
- [ ] 执行向量更新前持久标记 pending；仅全部写入及验证完成才标 ready。失败保留 repair task，返回明确同步待修复状态；检索按 dirty/repair 状态过滤或返回 index_unavailable，不能继续使用部分或旧向量。
- [ ] 启动 reconciliation 及显式 retry 修复相同 operation，不追加正文、不制造新笔记版本。模型／分块配置 fingerprint 改变继续走原重建流程和工作区门禁。
- [ ] 测试只改 A 不重建 B、删除零向量、移动双路径、正文成功后 embed／Chroma 中断、部分 upsert、空文档、重启修复、修复前 search 不返回陈旧内容。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_index_repairs.py tests/integration/test_retrieval_service.py tests/integration/test_notes_mutations.py -q`。提交 `fix(retrieval): repair per-file indexes and fence stale chunks`。

### B5：纯预览计划与共享修改冲突（原 Task 7）

**Files:** 新增 recovery/planner.py、tests/unit/test_recovery_planner.py；修改 recovery/schemas.py、models.py。

- [ ] 用 before boundary、当前活动分支及继承历史、边界后实际 owned mutations、later mutations 和当前 manifest 构建 RestorePlan；按操作逆序求受影响路径目标 bytes／目录集合。
- [ ] 只撤销 owned changes；他人后续操作或 external 修改即冲突，包括写回相同 bytes 的 ABA、移动交叉路径、文件夹中出现未追踪内容。全计划任一冲突则 can_apply=false。
- [ ] 返回原 API 合同的 file_changes、folder_changes、conflicts、affected_messages、requires_confirmation；记录 state_revision、workspace_seq、正文哈希、内容摘要及过期时间，preview 不改变正文／索引／活动 head。
- [ ] 测试本会话 A、他会话 B 时只撤销 A；他会话／Library／external 后改 A 时整次拦截；空目录／移动／边界后批准旧草稿；无正式写入仍允许仅状态恢复；旧导入历史不可恢复。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/unit/test_recovery_planner.py -q`。提交 `feat(recovery): preview owned changes and reject shared conflicts`。

### B6：整体恢复状态机、幂等重启和最后发布（原 Task 8）

**Files:** 新增 recovery/service.py、tests/integration/test_recovery_coordinator.py；修改 conversations/service.py、models.py、notes/mutations.py、retrieval/repairs.py、bootstrap/app.py。

- [ ] start 在独占门禁内重新验证 preview 身份、编辑正文摘要、seq/head/hash、确认字段、冲突和有效租约；持久化确定计划与 maintenance，再执行恢复。确认不得依赖前端弹窗自行保证。
- [ ] 顺序：prepared→restoring_files→reindexing→preparing_state→publishing→succeeded。每路径进度持久化；恢复为不存在即删除，目录仅按 manifest 安全操作；生成补偿 commit 保留其他会话文件。
- [ ] RAG 只修复受影响路径；校验全部正文与 index hash/fingerprint 一致后准备 fork。恢复原 UI 历史／摘要／草稿／工具状态，替换真实全工作区 notes_commit/seq，接受编辑后的用户消息一次。
- [ ] publish_recovery 在同一应用 DB 事务内 CAS 切换活动 branch/head/generation、发布 job 成功和 prepared_turn_id、清 maintenance。候选 checkpoint 提前写入但不提前可见。
- [ ] 失败保存 failed_stage/retryable；不可继续时维修状态保留，不能显示普通完成。续办相同计划，不按新的现场重新计算撤销范围；重启可找回 Git ref、候选配置和已完成路径。
- [ ] 故障注入覆盖 file_applied、git_committed、index_rebuilt、candidate_saved、before_publish、after_publish。重复 start/retry 返回同任务／结果；LLM 失败与已成功的恢复独立，原消息不能再次插入。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_recovery_coordinator.py tests/integration/test_turn_recovery_pg.py -q`。提交 `feat(recovery): coordinate durable file index and state restoration`。

### B7：恢复 API 与 prepared-turn 重推理（原 Task 9）

**Files:** 新增 recovery/router.py、tests/integration/test_recovery_api.py；修改 chat/router.py、schemas.py、bootstrap/app.py。

- [ ] 按 API-001 实现 POST `/conversations/{id}/recoveries/preview`、POST `/conversations/{id}/recoveries`、GET `/recoveries/{job_id}`、POST `/recoveries/{job_id}/retry`；写接口加入现有 same-origin 依赖。
- [ ] 返回 PreviewOut/JobOut 及统一 code/message/retryable。缺文件确认、preview 过期、身份跨会话、正文改变、冲突、busy 分别明确拒绝；客户端不能指定任意 paths/commit 作为恢复权威。
- [ ] `/chat` 的 question 和 prepared_turn_id 互斥；后者唯一 claim 已接受的用户消息，不再 prepare 一遍。详情返回活动恢复／待生成位置，刷新能续接。
- [ ] 测试确认 false 且有文件变化为 409 confirmation_required、冲突无正文变更、重复 prepared-turn 不重复模型调用、GET 任务在 maintenance 可用、所有写／读入口遵守 gate。
- [ ] 验证：`.venv\Scripts\python.exe -m pytest tests/integration/test_recovery_api.py tests/integration/test_checkpoint_chat_api.py -q`。提交 `feat(api): expose recovery jobs and prepared turn execution`。

### B8：用户消息编辑、确认弹窗、冲突和进度 UI（原 Task 10）

**Files:** 新增 MessageEditForm.vue、RecoveryConfirmDialog.vue、recovery.ts、frontend/tests/unit/message-recovery.spec.ts、frontend/tests/e2e/message-recovery.spec.ts；修改 MessageList.vue、UserMessageActions.vue、api.ts、store.ts、sse.ts 及 Library 的状态刷新入口。

- [ ] 每条 user 消息提供 16px 编辑／复制图标，title/aria-label 清晰。编辑用服务端身份，原文进入 textarea；未持久化／旧历史／忙状态给禁用原因，复制始终可用于可见原文。
- [ ] 同时只编辑一条；Enter 换行，Ctrl/Cmd+Enter 提交，Escape 取消，IME composing 不提交；空白仅用 trim 判空，发送保留原文，未改内容直接关闭。
- [ ] 编辑提交先检查未保存草稿，调用 preview；requires_confirmation=true 展示“确认回退已执行的文件改动”、文件／目录操作清单和“确认回退并重新生成／取消”。conflicts 显示原因，只能取消，不出现强制覆盖。
- [ ] start 前不截断历史。轮询真实 job 显示阶段与可重试错误；成功重新加载活动状态与 Library，用 prepared_turn_id 接续；刷新、切换会话及旧 SSE／旧轮询响应按 branch/generation/request token 隔离。
- [ ] 测试剪贴板拒绝、弹窗取消零 start、目录也要求确认、冲突拦截、重复点击、刷新续办、旧 SSE 不污染新分支、重推理失败仍保留恢复后的用户消息；legacy 页面走同一后端恢复合同。
- [ ] 在 frontend 运行 `npm run test:unit -- tests/unit/user-message-actions.spec.ts tests/unit/message-recovery.spec.ts`、`npm run test:e2e -- tests/e2e/message-recovery.spec.ts`、`npm run build`。提交 `feat(frontend): edit messages through confirmed recovery jobs`。

### B9：真实恢复演练、部署持久化及文档同步（原 Task 11—12）

**Files:** 新增 tests/integration/test_full_rollback_acceptance.py；修改现有部署文件、README.md、docs/01-architecture/database.md、docs/03-modules/chat/context-management.md、docs/03-modules/retrieval/retrieval.md、模块 README、docs/02-api/chat-tools.md、本目录索引和执行结果；同步独立上层文档仓库对应需求／模块／API／数据／测试／运维／追溯矩阵。

- [ ] 配置 notes 正文、NOTES_HISTORY_DIR、Chroma、PostgreSQL 均持久化。检查 history 不嵌套在 notes 内；启动 Git 不可用／仓库不可访问时返回可识别错误，不启用无历史保护的写入。
- [ ] 迁移运行手册包含停止旧 worker、备份 DB＋正文＋影子仓库、dry-run／apply、初始版本、索引核对、失败续办。明确旧 checkpoint 无历史正文版本时不能编辑；不可只回退代码而丢弃已写的新状态。
- [ ] 在隔离持久目录和数据库中做真实服务停止／重启演练：修改正文、发生索引失败、恢复任务半途停止、重开后维修和继续；不能用清空数据库再启动代替。
- [ ] 上层文档按独立版本、变更记录和追溯规则同步实际完成状态；实现文档不写独立版本。目标设计保留 review 状态，不伪造评审／冻结。上层仓库只本地记录，不推远端。
- [ ] 完成下节全部 G 项，执行全量回归和构建，回填真实结果／提交 SHA。提交 `docs: record rollback completion and recovery operations`。

## 6. 最终验收门槛：全部通过才称完成

| ID | 场景 | 必须观察到的结果 | 负责任务 |
|---|---|---|---|
| G01 | 正式聊天不调用旧消息写入，刷新／重启 | 消息、摘要、引用、工具、草稿来自同一活动 checkpoint | A2 |
| G02 | 压缩与旧会话重复导入 | UI 全文不丢；ID 稳定；重复导入无重复；不可恢复历史禁用 | A1—A3 |
| G03 | 并发发送、断开、续接、模型切换 | 单次接受用户；唯一执行 claim；无过期 head 覆盖 | A2 |
| G04 | 普通聊天／草稿编辑 vs 正式写入 | 前者无新笔记 commit；后者有完整版本、来源、seq 与状态关联 | B2—B3 |
| G05 | Library／草稿所有写入及文件夹操作 | 无绕过统一 mutation/gate 的正式写入入口 | B1—B3 |
| G06 | 单文件创建／修改／删除／移动 | 仅受影响路径重建／删除向量，hash/fingerprint 匹配，空文件允许零 chunk | B4 |
| G07 | 索引失败与重启修复 | 持久待办；旧向量不可检索；重试不改正文／不重复 append | B3—B4 |
| G08 | 编辑历史消息仅影响 A，其他会话改 B | A 恢复目标 bytes，B 不变；仅更新 A 索引；新活动分支正确 | B5—B7 |
| G09 | 其他会话／Library／external 后改 A，包括 ABA | 整次拦截，消息／正文／向量／head 保持，保留后续更改 | B5—B8 |
| G10 | 文件／目录变化确认与取消 | 取消零副作用；直接 API 绕过确认也被拒绝 | B7—B8 |
| G11 | 无文件改动的历史编辑 | 仍恢复状态与摘要／草稿并重新生成；无无意义 Git commit | B6—B8 |
| G12 | 各恢复阶段故障、真实进程重启 | 不提前发布 head；维修阻断；续办同计划；成功后解除 maintenance | B6、B9 |
| G13 | 发布后重复 start/retry／prepared-turn | 同一结果；修改后用户消息和生成请求均不重复接受 | B6—B7 |
| G14 | 两 worker、恢复和模型重建竞争 | DB 门禁有效，无部分正文／索引被其他请求读取 | B1、B7 |
| G15 | 复制／编辑／弹窗／切换／旧 SSE | 原文复制；失败反馈；服务端 ID；旧响应不覆盖新状态 | A3、B8 |
| G16 | 部署卷、备份、上层与代码文档追溯 | 重启保留全部存储；文档链接实际实现／测试／提交证据 | B9 |

G08 的确定性断言示例（在 test_full_rollback_acceptance.py 实现；helper 通过真实 HTTP／服务，不 mock 协调器）：

```python
async def test_rollback_updates_only_owned_file(recovery_harness):
    h = recovery_harness
    case = await h.conversation_with_approved_change("A.md")
    # case 包含 conversation_id/user_message_id/revision，以及 A 的修改前 bytes。
    await h.library_write("B.md", b"other session keeps this\n")
    preview = await h.preview(case, "modified question")
    assert preview.can_apply
    assert {item.path for item in preview.file_changes} == {"A.md"}
    job = await h.confirm_and_finish(preview, "modified question")
    assert job.status == "succeeded"
    assert h.read_bytes("A.md") == case.before_bytes
    assert h.read_bytes("B.md") == b"other session keeps this\n"
    assert h.index_repair_paths(job.id) == {"A.md"}
    assert h.index_matches_body("A.md")
    state = await h.get_state(case.conversation_id)
    assert state.values["notes_commit"] == h.current_commit()
    assert h.accepted_user_count(job.prepared_turn_id) == 1
```

上述额外 helper 在 tests/support/rollback.py 实现：library_write 走真实 mutation；preview/confirm_and_finish 走恢复接口并等待终态；read_bytes 读临时正文；index_repair_paths 查持久维修记录；index_matches_body 比较实际 Chroma／台账和当前正文 hash/fingerprint；accepted_user_count 查对应 prepared turn 的 checkpoint 展示消息，不统计 mock 调用。

最终命令（后端在项目根，前端在 frontend；在隔离验收环境运行，结果记录真实计数）：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --tb=short
.venv\Scripts\python.exe -m pytest tests/integration/test_full_rollback_acceptance.py -q --tb=short
.venv\Scripts\python.exe scripts/migrate_conversations.py --dry-run
```

```powershell
npm run test:unit
npm run test:e2e
npm run build
```

全量命令已包含最终验收文件时不必再重复运行第二条；保留其单独命令供调试。真实 PostgreSQL／Git／Chroma 验收不能被跳过并算完成；Playwright 的 stub 测试之外必须包含真实后端的 G08—G13 演练。阶段 A 完成报告只写“A 完成、B 待执行”，不得写“整体迁移完成”。

## 7. 交付给 Qoder 的执行指令

按本文件 A1→A2→A3→B1→B2→B3→B4→B5→B6→B7→B8→B9 顺序，先阅读上层依据及原计划合同，复用已有安全实现。每任务完成才勾选步骤并回填 results；任何失败保留失败证据。最终报告必须逐条列出 G01—G16 的实际结果和未完成项，不能以旧的 552 passed 宣布整体达标。本轮交付先留在任务分支供验收，合并／推送作为后续用户指令执行。
