# Checkpoint、影子 Git 与用户消息编辑回退 Implementation Plan

> **For agentic workers:** 按本计划逐项执行并回填复核证据。Qoder 在当前任务中顺序完成，每项使用 checkbox 跟踪；如安装了执行计划技能，可使用 superpowers:executing-plans。不要把本计划当作已实现说明，不要仅交付 UI 后宣布整体迁移完成。

**Goal:** 将会话与 Agent 状态迁移到持久化 LangGraph checkpoint，统一 notes 版本与按文件 RAG 修复，支持修改历史用户消息后安全恢复并重新生成，并为每条用户消息提供复制按钮。

**Architecture:** 保留现有 FastAPI、Vue、PostgreSQL、Markdown、Chroma 技术栈和可用的压缩算法。将会话持久化、图执行、正文变更、恢复协调分开，各模块通过小接口协作；checkpoint 负责状态，影子 Git 负责正文，恢复任务负责跨存储一致性。历史消息编辑创建新活动分支，不物理删除旧消息/旧 checkpoint，不对共享 notes 执行全树 reset。

**Tech Stack:** Python >=3.13、FastAPI、SQLAlchemy/Alembic、LangGraph 1.2.5（当前锁定）、AsyncPostgresSaver、psycopg、Git、Chroma、Vue 3/Pinia、Vitest、Playwright。

**Spec / 来源：**

- [REQ-018 整体回退需求](../../../../NoteAgent-docs/docs/02-requirements/REQ-018-历史消息编辑与整体回退.md)
- [ARC-001 目标架构](../../../../NoteAgent-docs/docs/03-architecture/ARC-001-目标架构与迁移边界.md)
- [ADR-002 技术取舍](../../../../NoteAgent-docs/docs/03-architecture/ADR/ADR-002-checkpoint与影子Git协同回退.md)
- [DATA-001 状态与材料版本](../../../../NoteAgent-docs/docs/06-data/DATA-001-状态与材料版本关系.md)
- [API-001 恢复接口约束](../../../../NoteAgent-docs/docs/05-interfaces/API-001-会话恢复接口约束.md)
- [TC-REQ-018-001 验收场景](../../../../NoteAgent-docs/docs/07-quality/TC-REQ-018-001-回退验收场景.md)
- 用户 2026-10-01 本轮补充：每条用户消息增加编辑与复制图标；实施需有针对性的代码分区与小重构；**共享修改冲突必须拦截且保留后续更改，有已执行文件变更要弹窗提示并确认**。

上层技术文档目前为 review。本轮用户已经要求制定整体实施计划并确认上述冲突/弹窗规则；执行者记录授权来源并同步 CR，不自行填写虚构评审人员、发布版本或冻结基线。

**执行状态：** 未执行。此任务只生成实施计划；以下测试是未来必须执行的检查，当前不声称通过。

## 1. 全局约束与明确范围

1. 按 A/B 两阶段迁移，A 完成状态存储/展示/压缩与旧数据迁移，B 完成 notes/RAG 协调及编辑重推理。A 阶段可以交付复制按钮；B 全部验收前编辑入口不得触发仅删消息的伪回退。
2. 现有消息全文、引用、工具步骤、pending_draft、摘要及压缩边界不能因迁移/压缩消失。UI 历史与模型工作上下文分别建模；框架并不会自动保留被应用删掉的消息。
3. 所有可恢复点绑定有效正文版本；无正文变化的多个 checkpoint 共享同一个 commit，修改草稿或普通聊天不触发 Git commit。节点中间状态可保存，但本期用户只能从安全轮次边界恢复。
4. 本期范围是 Agent/会话状态、notes 下现有 Markdown 与一层文件夹结构、RAG 派生索引。模型选择/密钥、外部服务副作用、网页历史、日志不纳入回退；后续多模态附件需另行扩展。
5. 只撤销当前会话活动分支在恢复边界之后的正文操作，保留其他会话/Library 的独立文件变化；同一路径有外来操作即冲突，不自动合并、不提供强制覆盖按钮。
6. 用户编辑第 N 条用户消息，恢复到**接收该条消息之前**的安全 checkpoint，再添加修改后的消息重新运行。原分支含该消息及后续历史仍保留，活动分支不显示原后续消息。复制保留消息原始文本、换行和 Markdown，不复制渲染 HTML。
7. 恢复预览列出将撤销的文件创建/修改/删除/移动和文件夹变化。有任何已执行文件/文件夹变化都需确认弹窗；冲突时只有提示和取消，不发送执行请求；取消后不改消息、正文、索引和活动指针。
8. 保存编辑后的正文先用 trim 判断是否为空；合法正文保留原换行。未修改正文的提交直接关闭编辑，不建立无意义分支。编辑不是仅修改显示文本。
9. 成功的统一恢复包括正文恢复、当前身份的索引修复、候选 checkpoint 校验、活动分支发布。新回答失败与恢复失败分别呈现；不能把生成失败再恢复成旧回答。
10. 共享笔记恢复采用短暂全工作区门禁，阻止并发读到半恢复正文/索引、写盘、新聊天和模型/索引切换。本期不尝试在活动流中抢占回退：有运行中会话时拒绝恢复，前端流式期间禁用编辑，复制仍可用。
11. 门禁、版本 CAS、恢复任务需要数据库级保护，不能只依赖 Pinia 标志或进程内 Lock。固定加锁顺序，见 §5；正常消息/工具记录有 generation 检查，旧回包不得写入新分支。
12. notes/、checkpoint、影子 Git、旧库备份均为用户数据，不提交工程仓库，不推远程；Git 快照只是恢复依据，不能当 PostgreSQL+Chroma 的原子事务。
13. 不改 `docs/references/`、`docs/roadmap/`、`TODO.md`；不覆盖 `docs-v1.5.0`、`docs-v1.5.1` 和既有评测结果。源码变更限定为本功能所需的模块接缝，不改学习笔记生成策略、Prompt 正文或无关样式。
14. 本库文档无独立版本；上层文档独立递增，原地修订和文末记录。不得因本计划自动创建产品发布/冻结快照。

## 2. 已核对的代码现状与切入点

依据代码仓库 HEAD `59c23210cf85138d5a851771f1c8d5f74e652b0f` 的实现与当前工作区；此前文档迁移尚未提交，Qoder 先记录实际工作区/提交状态，不丢弃既有差异。上层仓库初始提交 `7920169e44a0e6d3e3215916c71fcdc0e173b7e2`。

| 入口 | 当前职责/问题 | 本次处理 |
|---|---|---|
| `chat/router.py:chat_with` | 先写 user，再手动累计 SSE，最后写 assistant | 调用会话模块创建轮次，图模块持久化结果；HTTP 仅序列化事件 |
| `chat/agent.py:ChatAgent.stream` | while 工具循环、临时完整 ToolMessage、pack/compact、引用注册混在一起 | 保留对外 facade，将执行移入图节点；完整运行状态 checkpoint 化 |
| `chat/history.py:ConversationStore` | Conversation/Message CRUD、摘要、水位、草稿混合 | 旧数据导入/备用读路径保留；新增会话元数据与 checkpoint 门面 |
| `chat/drafts.py:DraftStore/commit_review` | 自建表草稿；先 pop，再写盘，索引异常吞掉 | 草稿写 checkpoint；审批走统一正文操作模块，写盘成功和索引未就绪分别记录 |
| `chat/context_pack.py/context_compact.py` | 当前纯函数与预算已可用，但类型依赖 history | 仅迁出数据记录类型依赖，继续使用预算/压缩行为 |
| `notes/router.py` | create/save/delete/move/folder 操作各自写盘和同步索引 | 调用统一 NotesMutationService；原 HTTP 结构兼容并增加状态字段 |
| `retrieval/service.py:index_note` | 已按文件先删旧向量再建，新元数据 `content_sha256` 是片段哈希 | 复用；增加正文级哈希与修复验收，不能拿片段哈希充当整文件哈希 |
| `model_management/service.py:read/write/chat` | 维护计数门禁只在当前进程中；read 维护期仍可用 | 保留运行快照职责；与持久化工作区门禁协作，避免塞入整个回退逻辑 |
| `bootstrap/app.py/runtime.py` | 同步 build_container/build_agent；现有生命周期未打开 saver | lifespan 打开/关闭异步 saver，注入会话/写入/恢复模块 |
| `MessageList.vue` | user 气泡纯文本，无操作按钮 | 增加独立 UserMessageActions 和 MessageEditForm |
| `chat/store.ts:ChatMessage` | 只有临时 key，加载时丢掉服务端 message.id | 保留 serverId/turnId/branchId/editable，SSE 回填稳定 ID |
| `AssistantPage.vue` | 组合消息、面板与 composer | 仅绑定编辑事件/恢复状态，不承担回退流程 |
| `prompt_eval/run.py`、`rag_eval/agent_run.py` | 用 SQLite ConversationStore 构造 ChatAgent | 切到真实图+内存 saver 测试模式，保持指标/报告格式，不留下旧 Agent 第二条运行路径 |
| `Dockerfile`/compose | 镜像没有 Git，影子库没有持久卷 | 第二阶段补 Git、影子仓库卷/备份说明 |

复制使用浏览器 Clipboard API，localhost/HTTPS 正常支持；无权限/非安全上下文要显示失败并保留手动选择文本，不宣称复制成功。

## 3. 代码分区：只拆本次需要的接缝

不把项目整体重命名为 DDD 分层，也不按每个新概念建一套空接口。以下文件承担实际行为，依赖通过构造参数注入，测试从同一模块入口调用。当前其他目录不搬家。

```text
src/noteagent/
├── conversations/                 # 会话元数据、状态持久化、历史展示/迁移
│   ├── __init__.py
│   ├── records.py                 # 纯记录类型；迁出 history 中的 DTO
│   ├── models.py                  # branch/run/恢复边界映射，Base 仍来自 db
│   ├── checkpoints.py             # AsyncPostgresSaver 生命周期和 config 适配
│   ├── service.py                 # 活动分支、消息/草稿读取、轮次准备、CAS
│   └── migration.py               # 只读旧表导入、核对、批次/能力边界
├── chat/
│   ├── agent.py                   # 薄 facade；不再保存第二套消息真相
│   ├── graph.py                   # 状态 schema、节点/边连接、compile
│   ├── nodes.py                   # compact/model/tools/finalize
│   ├── events.py                  # 图输出 -> 既有 SSE 合同
│   └── context_*.py               # 保留纯 pack/compact/budget，避免无关搬迁
├── notes/
│   ├── repository.py             # 路径校验与基础文件操作
│   ├── mutations.py              # 所有正式写入、版本记录、索引进度
│   └── versions.py               # 独立影子 Git 与目录 manifest
├── recovery/
│   ├── __init__.py
│   ├── models.py                 # workspace/mutation/recovery 持久记录
│   ├── schemas.py                # preview/job/error 合同
│   ├── gate.py                   # DB 门禁与固定加锁顺序
│   ├── planner.py                # 纯差异/所有权/冲突计算
│   ├── service.py                # preview/执行/重试/恢复后发布
│   └── router.py                 # HTTP 映射，不直接 Git/Chroma/改 checkpoint
└── retrieval/service.py           # 保留检索与按文件索引，补正文哈希验收

frontend/src/features/chat/
├── MessageList.vue
├── UserMessageActions.vue         # 编辑/复制图标、复制结果
├── MessageEditForm.vue            # 多行编辑、取消/保存并重新生成
├── recovery.ts                   # preview/确认/轮询/重新发送流程
├── api.ts                        # HTTP，无 DOM/弹窗
└── store.ts                      # 会话消息与面板状态，对 recovery 提供小接口
```

`recovery.ts` 使用聊天 store 公共方法，不另建一份消息列表或模型状态。`conversations/service.py` 不导入 HTTP，也不反向导入 recovery；recovery 依赖 conversations/notes/retrieval。`versions.py` 不知道会话和 LLM；`mutations.py` 通过 Origin 接收来源。图节点生成草稿，不直接写正式笔记。bootstrap 是跨模块装配点。

新增目录首次就创建实际内容及 `__init__.py`；为实际模块补简短 README。不建立仅转发一个函数的十层 adapter，不并存新旧 Agent 运行实现。

## 4. 状态与持久记录合同

以下为本计划规定的逻辑字段/接口，Qoder 按任务落实类型和校验。字段变更必须同步前后端和相关测试，不能自行改成“删除后续 messages 表行”。

### 4.1 GraphState 与安全恢复点

| 字段 | 内容与规则 |
|---|---|
| `schema_version` | 整数状态版本，初始 1；迁移校验拒绝无法识别的版本 |
| `ui_messages` | 完整用户/助手展示记录，保留 id、turn_id、created_at、citations、tool_steps；摘要不得覆盖或删减 |
| `working_records` | 模型窗口内的用户/助手及工具 stub 记录；保留 current turn、完成轮次和现有水位规则 |
| `running_summary` / `summary_watermark_turn_id` | 当前摘要与压缩边界，随 checkpoint 恢复，不能读取当前 Conversation 的旧摘要冒充历史 |
| `pending_draft` | 可 JSON 序列化的草稿，附 draft_id、来源会话/分支、产生轮次与基准文件哈希；没有则 null |
| `runtime_messages` | 当前轮完整 AI 工具调用和 ToolMessage，保留 tool_call_id 配对；完成轮清空，压缩不能破坏未完成配对 |
| `citation_registry` / `tool_steps` | 可序列化引用注册表和本轮工具展示步骤；禁止只保存在 ContextVar 中 |
| `current_turn_id` / `current_user_id` / `current_question` / `tool_rounds` | 当前运行信息，max_tool_hops 继续使用 ContextBudget |
| `branch_id` / `generation` | 应用逻辑分支与写入隔离代数；新恢复分支增加 generation |
| `notes_commit` / `workspace_seq` | 本状态接受时的全局正文版本和操作序号；A 阶段 notes_commit=null 且不可完整回退，B 基线后必须有效 |
| `run_status` | idle/prepared/running/completed/failed/interrupted；流式失败不能伪装为已完成 |

历史 UI 记录与工作记录内容有不同用途，不新建第二份 messages SQL 权威表。纯 `records.py` 定义 MessageRecord 和展示记录转换，旧 history 可以导入这些类型，context 算法不再依赖 DB CRUD。

checkpoint 的 `thread_id` 使用原 conversation UUID，namespace 保持应用固定值；**所有读取/更新都传明确 checkpoint_id**，不能用 saver 的“最新 checkpoint”代表活动分支。逻辑 branch_id 及 head config 由应用元数据管理，框架 fork 不替应用选择活动分支。

安全点是没有待运行节点的 idle/completed checkpoint。首次空会话建立一个安全点。发送前记录安全点到 UserMessageBoundary，随后持久化 user 消息，再运行图。第 N 条用户消息的编辑以对应 boundary 为源，不在 UI 里按消息数组下标猜 checkpoint。

B 阶段每次接收新 user 前，先将当前全局 notes_commit/workspace_seq 写入该安全点（无文件变化不新建 Git commit），再登记 boundary，避免上一次回答的旧工作区序号冒充本次发送时的边界。运行中图 checkpoint 的精确 config 保存到 conversation_runs.checkpoint_id；完整 UI 轮次开始/结束及草稿更新由会话模块 CAS 发布明确 head。启动发现未结束 run 标 interrupted，保留 run 的节点 checkpoint 供受控恢复；不能按 saver 全局 latest 猜它，也不能自动重跑 LLM。恢复到历史消息仍只选择安全 before_config，不能任意选择半执行工具节点。

正常草稿编辑/审批是从当前显式 head 创建新的安全状态版本，`as_node` 使用图内已定义的 `finalize` 节点使其后继为 END；测试断言 `snapshot.next == ()`。不要让 update_state 自动推断成旧工具节点并意外执行下一步。恢复得到候选安全 checkpoint，随后主动提交新轮次输入才开始推理；从 END 直接 `invoke(None)` 不会生成新回答。

### 4.2 PostgreSQL 应用表（新增 Alembic revision，不覆盖旧 migration）

| 记录 | 必需字段/唯一约束 |
|---|---|
| `conversations` 扩展 | active_branch_id、generation、state_backend、migration_batch_id；旧摘要/草稿字段暂保留，仅 legacy 模式读取 |
| `conversation_branches` | id、conversation_id、parent_branch_id、fork_checkpoint_id、head_checkpoint_id、checkpoint_ns、created_at |
| `conversation_runs` | id、conversation_id、branch_id、turn_id、user_message_id、generation、checkpoint_id、status、request_id UNIQUE、错误/时间；一次 prepared turn 只允许一个运行 claim |
| `user_message_boundaries` | conversation_id + branch_id + message_id UNIQUE、turn_id、明确 before_config、workspace_seq、recoverable、reason |
| `state_migration_batches` | batch_id、source counts/hash、target counts/hash、状态、核对结果；导入幂等，不重复创建根分支 |
| `workspace_state` | 单个工作区 id、head_commit、operation_seq、maintenance_job_id、generation；由部署持久配置固定标识，不能用每进程随机值 |
| `note_mutations` | operation_id UNIQUE、seq UNIQUE、origin（review/library/external/recovery）、owner conversation/branch、before/after commit、涉及 paths/folders 与哈希、index_fingerprint、进度、创建时间 |
| `recovery_previews` | preview_id、conversation/branch、目标 message、source head/revision、workspace_seq、index identity、编辑正文摘要哈希、差异/冲突、短期过期时间 |
| `recovery_jobs` | id、operation_id UNIQUE、source/target config、candidate config、新 branch/generation、expected head/seq、补偿 commit、路径/目录计划、每步进度、status/error、prepared_turn_id |

LangGraph 自己的 checkpoint 表由 saver.setup 管理，不手写仿 checkpoint 表，也不在应用 migration 里重复建其表。Alembic env 导入新增 ORM 模型以纳入 metadata。Base 始终只有一份。字段范围/索引与枚举在 schema 与 migration 一致。

### 4.3 模块公共入口

| 模块 | 输入/输出与约束 |
|---|---|
| `CheckpointRuntime.open()/close()` | async 生命周期，生产 AsyncPostgresSaver，测试可注入 InMemorySaver；SQLAlchemy DSN 转 psycopg URI，不打印凭据 |
| `ConversationService.get_state(conversation_id, config=None)` | async；返回 GraphState + 精确 config；默认使用元数据 active head，校验归属 |
| `ConversationService.list_messages(conversation_id)` | async；仅从活动 checkpoint 投影旧 MessageOut 合同，工具 stub 合并至对应助手 tool_steps |
| `ConversationService.prepare_turn(conversation_id, question, request_id)` | async；在会话 CAS 下持久化 user + boundary + run prepared，返回 PreparedTurn（run_id、turn_id、user_id、config、branch_id、generation） |
| `ConversationService.fork_for_edit(job)` | async；从 before_config 创建未发布候选状态，恢复历史/摘要/草稿，更新 notes_commit/workspace_seq、branch/generation，添加编辑后的新 user；同 job 重试复用候选，不重复加消息 |
| `ConversationService.publish_recovery(job)` | async；正文/索引已验证后 CAS 发布 branch/head/generation 并创建 prepared turn；与 job succeeded 标记在同一应用 DB 事务 |
| `NotesVersionStore.snapshot(parent_commit, operation_id)` | 记录 notes 正文与目录 manifest，返回 commit/changed paths；无差异返回原 commit；Git 对象 ID 是版本引用 |
| `NotesVersionStore.read_blob(commit, path)` | 返回 bytes 或不存在；commit/path 严格校验，不能执行用户提交的 ref |
| `NotesMutationService.apply(command, origin, operation_id, expected_hashes)` | async；统一校验/预日志/写盘/提交 Git/索引修复/状态关联，返回 MutationResult（commit、paths、index_status、operation_id） |
| `RecoveryPlanner.plan(boundary, owned_mutations, later_mutations, current_manifest)` | 纯函数返回 RestorePlan（before/after paths、folder 变更、冲突、期望哈希、undo 操作 ID）；不操作文件或 DB |
| `RecoveryService.preview(conversation_id, message_id, edited_content, expected_revision)` | async；只读预览/保存短期 preview，不改变正文、活动 head 和消息 |
| `RecoveryService.start(preview_id, edited_content, confirmed_file_changes, operation_id)` | async；验证预览、冲突、授权和 CAS，建立唯一持久恢复 job，返回 JobOut |
| `RecoveryService.retry(job_id, operation_id)` | async；只继续相同任务既定计划，不重新计算并误吞后来修改；认领锁保证单 worker |
| `WorkspaceGate.operation(mode)` | async contextmanager，mode=read/chat/mutate/recovery/model_rebuild；详见 §5 |

这些接口的内部返回数据类型在对应模块实际定义。不要让 HTTP handler 按顺序自行调用 Git/checkpoint/Chroma；恢复流程只有 RecoveryService 一个权威入口。

## 5. 文件、并发和失败语义

### 5.1 影子 Git 存放与正文版本

配置 `NOTES_HISTORY_DIR`，默认 `var/notes_history`，与 notes_dir 分开、与工程 `.git` 分开，生产目录持久化。使用独立 bare Git 对象库 + 临时 index，仅记录 notes 允许的 Markdown 路径和私有目录 manifest；不向 notes 写 `.git`，也不动工程 index/tag/HEAD。普通消息、摘要、草稿编辑只更新 checkpoint。

为避免 Windows CRLF、用户 Git attributes 或全局 excludes 改变正文语义，读取原始 bytes，用 `git hash-object -w --stdin` 写 blob，临时 `GIT_INDEX_FILE` 下 `read-tree` + `update-index` 写树，`write-tree`/`commit-tree` 生成 commit。参数使用 argv、shell=False，Git 子进程在非事件循环阻塞线程运行；operation_id 写 commit message 并建立保留 ref，让 DB 尚未绑定的已创建对象也不会被 GC。

空文件夹不能由 Git 默认记录，使用对象库私有 manifest 描述允许的一层目录，在 snapshot 中包含并在恢复时验证。禁止用用户 notes 根下的同名私有文件覆盖用户数据。Markdown bytes 原样恢复；索引读取现有文本规范化规则，正文验收比原始 bytes/哈希，片段验收比索引实际文本。拒绝 symlink/junction 指向根外，保留现有一层路径限制。文件夹操作存在未管理附件时保守拒绝，不递归删除附件。

初始化记录 notes 当前正文/目录为根版本，不重写用户文件，不创建每历史消息一个假 commit。正式写入前检测磁盘与最近接受 manifest 差异：受影响路径未管理改动按 external 操作记入历史/修复索引，或在修复失败时阻塞；不能偷偷把外部改动归到当前会话。

### 5.2 回退计算：不是 checkout 整棵旧树

1. 查询目标消息 before_config 的 workspace_seq，收集当前会话活动分支及其继承历史在该边界之后真正执行的 note_mutations；草稿审批以实际执行 seq 为准，不能只按草稿产生的 turn_id 判定。
2. 对这些操作逆序撤销，得到各路径的目标 bytes/存在性与目录集合；文件移动同时包含旧/新路径。生成对当前全局正文的**补偿 commit**，保留无关路径，不修改旧 Git 历史。
3. 任一待撤销路径在相关操作之后出现另一会话、Library、external 的操作，或磁盘哈希与已接受值不符，即冲突；即使最终字节相同也按操作归属识别冲突，防止 ABA 绕过。
4. 跨分支恢复只允许当前活动历史中可见用户消息的 boundary；旧分支恢复入口和分支浏览 UI 不在本期，旧历史保留供追溯。
5. 独立文件 A（当前会话写）和 B（另一会话写）只回退 A；A 被另一会话改过则整个本次恢复拒绝，不部分成功。preview/confirm/start 期间发生任何 seq/head/索引身份变化要重新预览。
6. 新候选 checkpoint 的 notes_commit 必须指向补偿后的全局正文版本，不直接照抄历史 before_config 的整树 commit；共享笔记当前事实仍可能包含其他会话的独立文件。

### 5.3 门禁与固定顺序

数据库 session advisory lock 对固定 workspace id 使用共享/独占模式；锁持有专用连接，结束/断连释放。读取/聊天持共享锁；正文变更、恢复、索引重建与模型运行快照切换持独占锁。尝试获取失败返回明确 busy，不无限等待 UI。现有 model_runtime 门禁继续负责本地快照和任务计数，不替代 DB 门禁。

统一顺序：`WorkspaceGate -> ModelRuntime 快照租约 -> conversation 行/CAS -> checkpoint 操作`。model-management worker 启动前取得独占 gate，并在工作线程执行完或进程失败后释放；不要在持 runtime Lock 后反向获取 gate。同步 API/worker 与异步 HTTP 通过同一个门禁约定，测试双连接/双进程互斥。

持久 `maintenance_job_id`/失败任务标识会阻塞新 read/chat/mutate，即使进程死后 advisory lock 自动释放也不能读到未修完的文件。状态查询、任务查询/重试允许；恢复期间文件正文读取也拒绝，不沿用 `_read_snapshot` “维护期始终可读”的旧行为。预览只在无恢复任务时执行，不持锁等待用户点弹窗；执行重新校验并获取独占锁。

同会话运行使用 run claim + generation/CAS 防止两个客户端并发发消息；工具/草稿写入及完成发布都验证 expected generation。服务端不得因为前端 streaming=false 就相信没有旧 run。客户端使用 ownerKey + branchId + generation + request token 丢弃过期 SSE/慢查询响应。

### 5.4 普通正文写入的失败协议

所有实际写入都先记录 operation_id 与 before/计划，保存可恢复原始 blob，才改磁盘；每步进度持久化。create(title)+append(content) 是一项操作、一份 after 版本，不能半创建变成成功。普通 Library 无正文变化不产生 commit。

Git/磁盘失败：没有完成版本记录的文件变更必须自动补偿到 before 或保留 repair_required 阻塞，不能返回普通成功。Git 已成功而 DB/草稿 checkpoint 未更新：启动/重试从 operation_id/ref 对账，不重复追加。索引失败：正文版本仍可记录为已写，但结果是 `index_pending`/`repair_required`，保留持久任务与检索隔离；用户不得误以为索引已同步。草稿写失败保留 pending_draft，正文已写但状态关联未完成时按操作去重，不能再次写盘。

审批绑定 draft_id、branch/generation、预览基准哈希和客户端 operation_id。恢复后旧 draft 的“同意”被拒绝，新分支恢复到的有效旧草稿需重新审批。出错时不要仅提前 pop 草稿后靠 best effort 塞回。

### 5.5 恢复任务顺序与崩溃处理

`prepared -> restoring_files -> reindexing -> preparing_state -> publishing -> succeeded`，出错为 failed（含 failed_stage、retryable，保留 maintenance）。任务先存计划、before manifest、目标 bytes/commit refs；每个文件/目录与每条索引修复进度可重试。

- restoring_files：仅按计划创建/替换/删除文件与目录；逐路径原子写入并校验。禁止全树 reset/clean。恢复为不存在只删该文件和向量；目录删除仅已知为空时执行。
- reindexing：当前 RetrievalService 身份不变时只重建受影响路径。`index_note()` 本身会删除旧片段；不存在路径 `delete_note()`。校验正文级 hash、片段内容/位置和当前 fingerprint，空 Markdown 零片段合法，不能用 is_indexed() 必须为 true 判断成功。
- preparing_state：从 before_config 创建隐藏候选；恢复摘要、工作窗口、草稿、引用和展示历史，附新正文版本，加入编辑后 user。候选 config 立即写 job；重试根据 job 查找同候选。
- publishing：应用 DB 事务中 CAS 更新 active branch/head/generation，并把 job 标 succeeded；事务先前任意阶段失败不发布新活动分支。解除 maintenance 也在该发布事务内。
- 生成新回答：成功 job 返回 prepared_turn_id，浏览器调用 `/chat` 的 prepared-turn 分支。服务端唯一 claim；重复点击/重连不重复加 user 或调用 LLM。恢复成功但 LLM 失败时展示“已恢复，重新生成失败”，保留新分支，可通过编辑/新的正常消息继续；不得报告“整体恢复失败”后偷偷回到旧分支。
- 启动：扫描未终态普通 mutation/recovery job，进行对账；未知状态 fail closed 并暴露可重试状态。不自动重跑 LLM 或重复用户批准过的写盘；显式重试只从已确认任务继续。重试时发现外部新修改/目标身份变化要拒绝并保留故障信息。
- 正文已经恢复但索引坏了时，GET job 可显示原消息恢复计划，其他正文/检索/新执行继续阻塞；不能让旧向量继续回答。修复不可用索引身份时先修复当前配置，完整校验通过才发布。

## 6. 前后端 HTTP / SSE 合同

### 6.1 兼容现有读接口

`GET /conversations` 保持 id/title/updated_at。`GET /conversations/{id}` 增加 branch_id、generation、state_revision（服务端不透明版本标识）、history_backend、recovery_available、prepared_turn_id、当前恢复任务摘要；pending_draft 从 checkpoint 读取。

`GET /conversations/{id}/messages` 仍为数组，原字段不变，增加 turn_id、branch_id、editable、edit_unavailable_reason。editable 必须由服务端按 boundary 能力/当前状态判断，旧导入消息无 before checkpoint 不能伪装可整体恢复。

`POST /chat` 增加 request_id、expected_revision；普通发送传 question，prepared-turn 发送传 prepared_turn_id，二者互斥。沿用 conversation_id/thread_id 兼容 alias。服务端持久化 ID 通过新增 `user_message` 事件回填 optimistic row，通过 `turn_complete` 返回 assistant id/head/revision；保留 conversation/thinking/generating/token/think/tool/tool_done/sources/answer/draft 的既有显示语义。

Vue 始终传 request_id/expected_revision；兼容旧 UI 的普通 question 请求可省略这两项，由服务端生成 request_id、验证当前会话存在并在自己的 CAS 下准备新轮次。prepared_turn 请求必须传 expected_revision/request_id，不能走该兼容降级。user_message 事件包含 request_id/user_message_id/turn_id/branch_id/generation，前端按请求身份替换对应 optimistic row 的 ID，不能按正文内容匹配。

每轮事件增加 run/branch/generation 归属信息（保留旧 token data 形状，通过 turn_started/turn_complete 提供上下文，禁止随意把字符串全部改对象破坏旧消费者）。`user_message` 必须早于 tokens，`turn_complete` 必须在 durable checkpoint/头指针更新之后。若最终提交失败，发 error 并标 run failed/interrupted，不假发完成。

### 6.2 新恢复接口

| 方法/路径 | 请求 | 响应及约束 |
|---|---|---|
| `POST /conversations/{id}/recoveries/preview` | message_id、edited_content、expected_revision | 200 PreviewOut，校验 user 消息与归属；只读预览 |
| `POST /conversations/{id}/recoveries` | preview_id、edited_content、confirmed_file_changes、operation_id | 202 JobOut；再次验证并持久认领，禁止直接信任路径/commit；有文件变化而 false 为 409 confirmation_required |
| `GET /recoveries/{job_id}` | 无 | 200 JobOut，仅任务进度/冲突/必要差异，不传完整正文/密钥 |
| `POST /recoveries/{job_id}/retry` | operation_id | 相同已确认 job 幂等重试；retryable=false 为 409，成功任务返回原结果 |

PreviewOut 字段：preview_id、conversation_id、branch_id、state_revision、workspace_seq、expires_at、message_id、affected_messages、file_changes（path/from_path、change_type、当前/目标摘要）、folder_changes、conflicts（path/reason）、requires_confirmation、can_apply。

JobOut 字段：id、conversation_id、status、stage、completed_paths/total_paths、error（code/message/retryable）、new_branch_id、new_state_revision、prepared_turn_id；运行阶段 prepared_turn_id=null，成功才给出。

错误码：404 conversation_not_found/message_not_found/job_not_found；409 busy/state_changed/preview_expired/rollback_conflict/history_not_recoverable/confirmation_required/stale_draft/turn_already_claimed；503 index_unavailable/repair_required；422 invalid_request。每个结构统一 code/message/retryable，冲突/过期必须重新 preview，不能原样重试 start。所有新增写接口接 require_same_origin，不在日志记录正文/凭据；路径与旧 NotePathError 映射保持一致。

### 6.3 用户消息按钮与编辑流程

- user 气泡下方一排 16px 编辑/复制 SVG 图标，无新增图标依赖；桌面 hover/focus-within 可强调，触屏始终可发现。button 的 title/aria-label 分别为“编辑消息”“复制消息”，可键盘触发。
- `ChatMessage` 保留临时 key 并新增 serverId、turnId、branchId、generation、editable、editUnavailableReason。不能把数组 index/key 当数据库 ID；尚未持久化的消息编辑按钮禁用并说明，复制可用。
- 复制直接在点击 handler 调用 `navigator.clipboard.writeText(message.content)`，在权限失效/缺 API 时反馈“复制失败，请手动选择文本复制”。成功提示“已复制”，不显示“保存成功”、不走后端、不插入 assistant 提示气泡。
- 编辑变为气泡内多行 textarea，初值原正文，按钮“取消”“保存并重新生成”。Enter 默认换行；Ctrl/Cmd+Enter 提交，Escape 取消（中文 IME composing 期间不触发提交）。一次只编辑一条，同步门闩在首次 await 前置位。
- 提交前处理右侧未保存草稿/引用正文：确认放弃或用户取消；同时检查任一缓存面板是否打开了受影响文件，不能恢复后把旧未保存正文再次写回覆盖恢复结果。
- preview.can_apply=false：显示冲突路径及“已有后续更改，本次未回退”，不出现“仍然覆盖”按钮。取消保留 textarea 中用户输入。
- requires_confirmation=true：弹窗标题“确认回退已执行的文件更改”，正文“该消息及后续操作已修改以下笔记。继续会恢复这些笔记并重新建立索引，后续回答将重新生成。”列出路径和操作；按钮“确认回退并重新生成”/“取消”。不要求用户理解 checkpoint/Git。任何 folder_changes 也要列出。
- 无文件变化：编辑表单明确后续回答会重算，提交后仍走 preview/start（confirmed_file_changes=false），不额外打断式文件确认弹窗。
- 开始恢复后显示阶段/失败/重试；不乐观截断历史或改原消息。成功后重新读取活动历史、清理受影响面板缓存并刷新 Library，使用 prepared_turn_id 发起重推理。换会话时旧 job 只更新其所属会话，不覆盖当前显示。
- streaming、恢复中、未确认的维护任务期间禁用编辑/发送/审批/Library 写入；复制原可见文本不受影响。首次刷新/重启按 detail/job 状态恢复 UI 门禁，不能仅靠内存 flag。
- 本期 Vue 实现新增入口；legacy 页面保持现有聊天/审批/Library 合同可用但不新增回退按钮。prepared-turn 路径仅新 UI 使用，避免引入两套回退交互实现。

## 7. 任务与验证步骤

所有任务先增加失败测试，再实现，再运行任务相关检查。每任务完成留局部提交，仅 add 本任务列出的文件；不要 git add -A 混入个人文件或此前整库文档迁移。若运行命令环境缺失必须记录失败原因，不能以 skip 代替阶段验收。

下列 Python 路径简写（如 `conversations/service.py`、`chat/router.py`）统一相对于 `src/noteagent/`；`frontend/`、`tests/`、`scripts/`、`docs/`、`alembic/`、Docker 文件和依赖文件相对于仓库根。任务列举的 `{a,b}.py` 表示两个实际文件，不创建带花括号的文件名。Task 10 的 MessageEditForm/UserMessageActions/MessageList 均在 `frontend/src/features/chat/`。

### Task 0：执行基线、合同与测试夹具

**Files:** 本计划；`docs/05-records/plans/2026-10-01-checkpoint-shadow-git-rollback-results.md`（执行时创建）；`tests/conftest.py`（新增或扩展现有）；`frontend/tests/fixtures/api.ts`；上层 REQ-018/API-001/DATA-001/TC-REQ-018-001/CR-2026-001。

**Produces:** 统一测试夹具 `conversation_harness`（真实 graph+InMemorySaver+临时 notes+确定性 FakeChatModel）、`postgres_harness`（同接口、实际临时 PostgreSQL schema、可以 close/reopen）、`recovery_harness`（真实影子 Git+临时 Chroma+确定性假 Embedder+可注入故障）、`rollbackApp`（HTTP TestClient，通过 lifespan 打开 saver）。夹具只使用测试路径，提供 client、service、notes、versions、retrieval、gate、get_state/get_job 与 stage fault 注入；不能 stub 掉待测整个恢复模块。

夹具 helper 必须在测试支持文件中实际实现，并复用真实公共接口。下列名称是本文测试片段的明确合同，不是已有生产代码：

| helper | 实现要求 |
|---|---|
| `create_conversation()` | async，创建元数据及空终态 graph checkpoint，返回含 id 的记录 |
| `create_unpublished_fork(conversation_id, config)` | async，真实图 update_state fork，但不发布应用 active head，返回 config |
| `complete_turn(conversation_id, question, force_compact=False)` | async，prepare_turn 后真实执行图；force_compact 通过测试 ContextBudget 缩小阈值触发，而非伪造 summary |
| `conversation_with_approved_change(path)` | async，完成生成与真实 draft 审批，通过 NotesMutationService 改 path，返回 conversation_id/user_message_id |
| `active_head(conversation_id)` | async，读应用 active head config，不读 saver latest |
| `start_edit(message_id, content, confirm)` | async，按 message 归属调用真实 preview/start，传确认标志，返回 JobOut |
| `wait_job(job_id)` / `get_job(job_id)` | async，等待本地 worker 有界结束/读取持久任务；超时失败，不无限 sleep |
| `fail_once(stage)` | 为下一次对应持久阶段注入一次异常，不替代 coordinator 实现 |
| `reopen()` / `retry(job_id)` | async，关闭并重建 app/saver连接/worker后，读取同一 DB 与 Git/Chroma，再调用真实 retry |
| `can_search()` | async，通过 gate+实际检索入口检查可用性，维护阻塞返回 false |
| `note_and_index_match(path)` | async，读真实 bytes、正文级哈希、当前身份和片段集合逐项比对 |

Task 0 建支持文件/合同；依赖生产模块的 helper 随对应任务补齐后立即跑测试，不在 Task 0 写一批空 pass/成功 stub。夹具及 Task 7/10 的本地 case factories 只属于测试，不进入生产模块公共接口。

- [ ] 记录 `git status --short`、HEAD、上层 HEAD、受保护文件哈希及本机 Git/Python/Node/PostgreSQL 版本。确认此前文档迁移差异保留，不 reset/clean。
- [ ] 运行现有关键测试建立基线，保存实际结果，修复仅本任务引入的失败：

```powershell
uv run pytest tests/unit/test_chat_history.py tests/unit/test_context_pack.py tests/unit/test_context_compact.py tests/unit/test_drafts.py tests/integration/test_app.py tests/integration/test_notes_api.py -q
npm --prefix frontend run test:unit -- tests/unit/chat-state.spec.ts tests/unit/sse.spec.ts
```

- [ ] 在上层文档原地补本轮冲突拦截、文件变化确认、用户消息复制/编辑规则与具体接口；兼容增强递增 minor、修订日期/记录，仍保留真实评审状态，CR 写明本轮执行授权。不得为旧无历史文件消息承诺完整回退。
- [ ] 夹具定义 `fail_stage` 支持 file_applied、git_committed、index_rebuilt、candidate_saved、before_publish、after_publish，故障每次只触发一次；实现真实快照断言，给两个并发连接各自独立会话。
- [ ] 自检 Task 1～12 的公共类型与该夹具一致；对不可恢复的旧消息、目录操作和空文件都有 fixtures。

### Task 1（A）：会话记录拆分、元数据与 PostgreSQL saver

**Create:** `conversations/{__init__,records,models,checkpoints,service}.py`；新的 Alembic revision；`tests/unit/test_conversation_state.py`；`tests/integration/test_postgres_checkpoints.py`。
**Modify:** `chat/history.py`、`chat/context_pack.py`、`chat/context_compact.py`、`db/__init__.py`、`alembic/env.py`、`bootstrap/app.py`、`pyproject.toml`、`uv.lock`。

**Consumes/Produces:** 保留旧 ConversationStore 作为 legacy 导入入口；提供 §4.3 CheckpointRuntime/ConversationService，records 类型不含 Session/HTTP，生产异步 saver 与测试内存 saver使用同一状态模型。

- [ ] 测试创建空会话、显式 head 查询、同一会话两个分支读取不串最新 checkpoint、JSON 状态持久化与关闭重开。
- [ ] 在不升级现有锁定 LangGraph/LangChain 的前提下添加缺少的 saver/pool依赖，并检查锁文件 diff：

```powershell
uv add langgraph-checkpoint-postgres "psycopg[binary,pool]"
uv lock --check
```

- [ ] `AsyncPostgresSaver.from_conn_string` 由 async 生命周期持有，首次受控 setup（部署/启动初始化需数据库级互斥），池化若使用 psycopg_pool 也必须 lifespan 打开关闭。build_container 不创建无法关闭的短期 saver。SQLAlchemy URL 转 PostgreSQL URI 使用 URL 工具正确编码，不做字符串打印。
- [ ] 类型迁出 history；旧算法输入仍为 MessageRecord，当前数据表不 drop。metadata 新字段及唯一约束随 migration 添加，测试数据库 create_all 导入完整 Base metadata。
- [ ] 应用 lifespan 支持已有 TestClient 测试夹具，也支持无真实 DB 的内存 saver；新测试使用 `with TestClient(app)`，不把生产替成 MemorySaver。

代表断言（夹具与公共方法由 Task 0/1 定义）：

```python
async def test_active_head_is_not_savers_latest(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    original = await h.service.get_state(c.id)
    abandoned = await h.create_unpublished_fork(c.id, original.config)
    shown = await h.service.get_state(c.id)
    assert shown.config == original.config
    assert shown.config != abandoned.config
```

运行 `uv run pytest tests/unit/test_conversation_state.py tests/integration/test_postgres_checkpoints.py tests/unit/test_context_pack.py tests/unit/test_context_compact.py -q`，期望新旧测试通过。PostgreSQL 测试必须实际关闭/重连，内存 saver 通过不等于持久化通过。

### Task 2（A）：将 Agent 循环改为可持久化图执行

**Create:** `chat/graph.py`、`chat/nodes.py`、`chat/events.py`、`tests/unit/test_chat_graph.py`。
**Modify:** `chat/agent.py`、`chat/citations.py`、`chat/tools.py`、`chat/drafts.py`、`bootstrap/runtime.py`；既有 Agent/工具/上下文测试。

**Graph:** `START -> compact -> model -> (tools -> compact -> model)* -> finalize -> END`。model 生成工具调用时转 tools，达到预算限制或异常转明确失败收尾；finalize 保存 UI 助手结果/引用/步骤并清理已结束 runtime_messages。prepare_turn 在运行前持久化 user，节点不得重复添加。

- [ ] 先测试多次 tool hop 后暂停/恢复时工具调用 ID 与结果配对、摘要不删除 ui_messages、max_tool_hops 及 source heading tree 行为、引用编号、draft 状态重启恢复。
- [ ] 原 pack/compact 纯函数继续使用；异步 summarizer 用 `ainvoke`，不在事件循环内同步 invoke。当前预算参数不改成框架默认值；本次不强行套 SummarizationMiddleware 替换已经有行为约束的算法。
- [ ] 每节点持久化可序列化增量状态。propose_note 改为输出 draft 更新/由 tools 节点提交 draft，禁止工具闭包调用独立 saver 产生同轮竞争状态。current_* ContextVar 只做局部执行上下文，恢复真相来自 state。
- [ ] 图 stream 适配保留原 SSE，tool-hop 中 prose/reasoning 不进主回答。持久化工具完整 payload 只在进行轮保留，最终留展示 stub；失败保留可解释 run_status，不把截断正文标 final。
- [ ] 订阅图 checkpoint stream 的明确 config 事件并保存 run checkpoint 指针（锁定版本支持的格式必须有回归测试）；事件在 saver 真正保存后才接受。进度仅用于恢复该 run，不让中间 config 覆盖另一分支 active head。正常完成时通过会话模块 CAS 发布最后 checkpoint，SSE turn_complete 随后发出。
- [ ] 在实际安装的 LangGraph 1.2.5 下验证 `astream` 的自定义事件/节点更新接口再实现，禁止照搬与锁定版本不符的 stream_events v3 例子。对 models 的切换仅更换 model/tools/budget 依赖，共享同一会话 saver，状态和 head 不随 agent 对象重建而丢失。
- [ ] update_draft_content/review 的状态变更 async 化或明确桥接，不在 async handler 中嵌套 asyncio.run。ChatAgent 保留薄的 stream facade，HTTP 不另存 assistant，唯一存储在图 finalize。

```python
async def test_compaction_keeps_display_history(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    await h.complete_turn(c.id, "第一条需要保留的材料")
    await h.complete_turn(c.id, "第二条材料", force_compact=True)
    state = await h.service.get_state(c.id)
    displayed = await h.service.list_messages(c.id)
    assert displayed[0].content == "第一条需要保留的材料"
    assert state.values["running_summary"]
    assert len(state.values["working_records"]) < len(state.values["ui_messages"])
```

运行 `uv run pytest tests/unit/test_chat_graph.py tests/unit/test_chat_agent_context.py tests/unit/test_context_pack.py tests/unit/test_context_compact.py tests/unit/test_chat_tools.py tests/unit/test_citations.py -q`。

### Task 3（A）：旧消息导入、读写切换与评测兼容

**Create:** `conversations/migration.py`、`scripts/migrate_conversation_state.py`、`tests/integration/test_conversation_migration.py`。
**Modify:** `chat/router.py`、`chat/schemas.py`、`chat/history.py`、`db/models.py`、`prompt_eval/run.py`、`rag_eval/agent_run.py`、相关 eval 单测/`tests/integration/test_app.py`。

- [ ] 建立 dry-run、apply、verify 三个 CLI 子模式。离线备份/停写窗口内导入，script 只访问用户指定 DB，输出 counts/hash/error，不记录正文/凭据。迁移边界按实际一整个导入快照计算，**不伪造每条旧消息的 before checkpoint、运行节点或文件版本**。
- [ ] 展示消息按旧 created_at 与旧读取顺序保持稳定，保存旧 message ID、turn_id（null 保留，不根据文本猜轮次）、引用、tool steps、摘要/水位和草稿；保留 raw tool stub 信息但不能当完整 ToolMessage/可重执行工具结果。
- [ ] imported root 形成一个安全 checkpoint，旧历史全部可显示/复制；旧消息 editable=false，reason 指明缺历史文件/状态。B 基线后新产生消息才可完整恢复。摘要中已经包含旧历史不重复压缩。
- [ ] 每个会话 counts/hash/草稿/水位验证通过才 CAS 改 `state_backend=checkpoint`；失败保持 legacy，不双写两份权威消息。旧表此版本不 drop；迁移前 legacy 只读/离线备份保留，切换之后新增 checkpoint 数据不能靠简单切 legacy 无损还原。
- [ ] 新运行读写只走 ConversationsService/graph；legacy 对未迁移会话只提供只读历史与明确迁移提示，不能在切换窗口偷写旧表。新创建会话默认 checkpoint。
- [ ] 评测/测试改用同一真实图和内存 saver，记录历史/工具步骤继续从 ConversationsService 提取，报告 schema/run 身份不变；已有 tests 不被“全部改 mock返回成功”规避。

```powershell
uv run python scripts/migrate_conversation_state.py --dry-run
uv run python scripts/migrate_conversation_state.py --apply --batch-id checkpoint-migration-2026-10-01
uv run python scripts/migrate_conversation_state.py --verify --batch-id checkpoint-migration-2026-10-01
uv run pytest tests/integration/test_conversation_migration.py tests/integration/test_app.py tests/unit/test_prompt_eval_run.py tests/unit/test_rag_agent_eval.py -q
```

CLI 实际 DB 取既有 Settings，生产执行前有真实备份；dry-run 不建立生产 checkpoint。验收含重复 apply 幂等和一条失败数据不切换该会话。完整旧消息中包含未配对 tool 时仍可展示，不伪造断点继续。

### Task 4（A）：稳定消息 ID、复制按钮和前端合同

**Create:** `frontend/src/features/chat/UserMessageActions.vue`、`frontend/tests/unit/message-actions.spec.ts`。
**Modify:** `chat/router.py/schemas.py`、`frontend/src/shared/api/types.ts`、`frontend/src/features/chat/{store,api,sse}.ts`、`frontend/src/features/chat/MessageList.vue`、`frontend/tests/fixtures/api.ts`、`frontend/tests/unit/sse.spec.ts`、`frontend/tests/e2e/assistant.spec.ts`。

- [ ] Message/ChatMessage 加 §6 字段，fromServerMessage 保留 server ID，新增 SSE ack/turn_complete 的解码测试与 ID 映射，临时 key 不覆盖 service id。
- [ ] `UserMessageActions` 接收 `content`/`canEdit`/`editReason`，emit('edit')。A 阶段编辑按钮 disabled，reason 为完整回退迁移未完成；每条 user 复制可用。不要给助手文本新增用户未要求的编辑行为。
- [ ] 复制成功/失败反馈在组件局部 `aria-live=polite`，避免改 showSaveToast 的固定“保存”语义和全局插入消息。按钮 SVG 内 aria-hidden，按钮本身 accessible label。
- [ ] Clipboard 在点击中直接调用，不先等待网络/预览，以保留用户手势；捕获异常和 API 不存在，原内容不 trim、不 parse Markdown。

可直接实现的核心函数：

```typescript
async function copyMessage(content: string): Promise<'copied' | 'failed'> {
  if (!navigator.clipboard?.writeText) return 'failed'
  try {
    await navigator.clipboard.writeText(content)
    return 'copied'
  } catch {
    return 'failed'
  }
}
```

单测 stub writeText（成功+reject+undefined）并断言精确 `"  原文\n第二行 **Markdown**  "`；E2E 用 localhost 上真实点击/Clipboard permission 或 addInitScript 测浏览器写入，必须断言用户文本含换行，不只测图标可见。

```powershell
npm --prefix frontend run test:unit -- tests/unit/message-actions.spec.ts tests/unit/chat-state.spec.ts tests/unit/sse.spec.ts
npm --prefix frontend run test:e2e -- tests/e2e/assistant.spec.ts
npm --prefix frontend run type-check
```

**A 阶段门槛：** 真 PostgreSQL 重启恢复、导入核对、完整历史/压缩分离、草稿和工具/引用展示、模型切换后状态不丢、复制全部通过。编辑与整体回退仍禁用。记录 A 的代码 commit 和结果，之后进入 B。

### Task 5（B）：影子 Git 与目录快照

**Create:** `notes/versions.py`、`tests/unit/test_notes_versions.py`。
**Modify:** `bootstrap/settings.py/app.py`、`Dockerfile`、`docker-compose.yml`；新增配置/运维说明。

- [ ] 用真实临时 bare Git 做测试：初始化不改工作树、byte roundtrip、中文空格路径、CRLF/LF、创建/删除/移动、空目录 manifest、无差异返回同 commit、禁止根外/symlink/junction、工程 Git index/HEAD 不变。
- [ ] 按 §5.1 实现 snapshot/read_blob，记录 operation_id/ref，使 crash 后可按该 operation 对账，不重复 commit。Git 无 identity 时使用影子库局部固定机器作者，不改用户全局 git config。
- [ ] `NOTES_HISTORY_DIR` 默认在 var，启动先检查 Git 可用；缺失时 recovery_available=false 且禁止承诺版本化写入成功，错误信息说清依赖。B 生产启动不得静默退回无版本写盘。
- [ ] Docker apt 包增加 git；compose 新 `notes_history` 持久卷只挂该目录，不挂整个 /app/var 遮住模型。容器重建后版本/ref/manifest 仍在；备份包含 PostgreSQL+notes+notes_history+模型索引配置，Chroma可重建但不能省略正文版本。
- [ ] 不立即对现有生产 notes 执行测试快照/覆盖。B 上线受控初始化后为 active heads 增加基线版本，仅新 boundary 宣称完整恢复。

```powershell
uv run pytest tests/unit/test_notes_versions.py tests/unit/test_settings.py -q
docker compose config
```

### Task 6（B）：持久门禁与所有正文变更统一入口

**Create:** `recovery/{__init__,models,gate}.py`、`notes/mutations.py`、第二个 Alembic revision、`tests/unit/test_notes_mutations.py`、`tests/integration/test_workspace_gate.py`。
**Modify:** `notes/router.py`、`chat/drafts.py/tools.py/router.py`、`model_management/router.py/service.py`、`bootstrap/app.py/runtime.py`、`scripts/index_notes.py`、`tests/integration/test_notes_api.py`、`tests/unit/test_drafts.py`。

- [ ] 测试 create/append/replace/delete/move/folder 操作只记一份 mutation，origin 正确；磁盘成功索引失败有持久 index_pending；写失败保留草稿；重复 operation_id 不重复追加；被恢复后的旧 draft/旧 generation 拒绝。
- [ ] 实现 Origin（source、conversation_id/branch_id 可空、draft_id/turn_id、generation），Command 的 action 对应现有写/目录动作，expected_hashes 对关联路径做 CAS。Library/引用侧栏来源为 library，不能记成当前会话自动生成。
- [ ] 使用 NotesMutationService 覆盖当前所有 notes/router 写路径及 commit_review，去掉重复 best-effort 索引代码。直接文件读接口在持久 maintenance 时不读取部分恢复内容。文件夹重命名/删除也是统一复合操作，检查未管理文件再落盘。
- [ ] 图工具仍只 propose，不直接写盘。approve/reject/update draft 通过当前显式活动 checkpoint；审批成功状态更新绑定 mutation，不提前 clear 后失去重试依据。
- [ ] `WorkspaceGate` 对 PostgreSQL 两连接/两进程验证，运行中 chat 与 recovery 冲突，维护失败后重启仍阻塞，GET job/status 能用。尝试不阻塞无期限，固定顺序不死锁，SSE 断开正常释放 lease。
- [ ] 模型/embedding 切换 worker 接入同一 gate；脚本 index_notes 使用受控维护锁，不允许恢复期间重建污染。评测写临时 notes 可以绕过生产 gate，但测试路径校验明确，不为生产开放 bypass 参数。
- [ ] checkpoint notes_commit/workspace_seq 在批准写成功后关联当前会话；其他会话新发言以当前全局正文版本接受安全点。no-change草稿批准可清草稿但不生成 Git commit。

```powershell
uv run pytest tests/unit/test_notes_mutations.py tests/unit/test_drafts.py tests/integration/test_notes_api.py tests/integration/test_workspace_gate.py tests/integration/test_model_settings_api.py -q
```

### Task 7（B）：纯恢复规划与预览冲突

**Create:** `recovery/planner.py`、`recovery/schemas.py`、`tests/unit/test_recovery_planner.py`。
**Produces:** §4.3 RecoveryPlanner/RestorePlan、§6 PreviewOut/JobOut；输入真实 operation seq/所有权/hash，输出计划，不做副作用。

- [ ] 测试当前会话多次修改同一文件逆序恢复、A/B 独立路径、外来同路径修改、ABA 同字节外来写、未记录磁盘更改、移动源/目标冲突、目录删除后新文件占用、旧 boundary 无完整恢复能力。
- [ ] 将 before checkpoint+workspace_seq+当前分支继承范围作为起点，以实际 mutation seq 判断哪些审批发生在边界后；不要仅用 git diff 两个树推断“本会话所有权”。
- [ ] 无正文差异且无目录差异不需文件确认；曾执行变更即使最终净字节差异为零，也在预览展示撤销操作，并按 §1.7 要求确认，避免忽略用户已经批准过的副作用。
- [ ] Preview token 存 server-side，绑定编辑正文 SHA-256、活动 head/revision、全局 seq、index identity、消息归属和到期（建议 5 分钟）；GET 不是 trusted write token，start 必须复查。

表驱动断言示例：

```python
def test_foreign_write_to_affected_path_is_conflict(planner_case):
    case = planner_case(
        own=[("append", "A.md", b"old", b"mine")],
        later_foreign=[("replace", "A.md", b"mine", b"new")],
    )
    plan = case.plan()
    assert not plan.can_apply
    assert [c.path for c in plan.conflicts] == ["A.md"]
    assert case.notes.read_bytes("A.md") == b"new"
```

`planner_case` 由该任务在测试文件实现，生成严格递增 seq 与固定边界/branch；不能只返回预置 plan。运行 `uv run pytest tests/unit/test_recovery_planner.py -q`。

### Task 8（B）：持久恢复协调器与 RAG 校验

**Create:** `recovery/service.py`、`tests/integration/test_recovery_service.py`、`tests/integration/test_recovery_restart.py`。
**Modify:** `retrieval/service.py`、`conversations/service.py`、`bootstrap/app.py`。

- [ ] 测试真实 A.md/B.md，只调用 A 的重建，B 内容与点集不变；删除无孤儿片段、移动旧/新路径正确、空 Markdown 零片段合法。Fake Embedder 可确定性编码，但 Chroma/版本库必须是真实临时实例。
- [ ] Retrieval metadata 增加正文级 note_content_sha256（保留既有片段 content_sha256）。无此字段的旧索引不要靠默认值伪通过：上线校验/重建或要求 repair；必要时按既有 index fingerprint 规范递增元数据版本并受控全库重建一次，该初始化重建不等于每次回退全库重建。
- [ ] 实现 §5.5 每阶段持久化/幂等重试；启动发现未完成任务只对账与阻塞，不自动执行 LLM。索引身份不可用拒绝 start；start 后身份/外部文件变动检测到也不忽略。
- [ ] 候选 checkpoint 保存 job_id/operation_id 身份，DB update 前失败可重新发现，不重复创建 fork。严格 source CAS，用户消息/分支归属再次校验。
- [ ] publish 应用 DB 事务同步 head/generation、job 成功和 maintenance 释放；不得把 saver 写入和本事务说成一笔原子事务，隐藏候选+提交指针就是补偿协议。
- [ ] 对 file_applied/git_committed/index_rebuilt/candidate_saved/before_publish/after_publish 各自故障注入，关闭并重开应用后重试，同 operation 最终正文/向量/状态只有一个结果。after_publish 响应丢失返回原 succeeded；不能重复 undo 或重新发 LLM。

```python
async def test_index_failure_never_publishes_new_branch(recovery_harness):
    h = recovery_harness
    case = await h.conversation_with_approved_change("A.md")
    old_head = await h.active_head(case.conversation_id)
    h.fail_once("index_rebuilt")
    job = await h.start_edit(case.user_message_id, "修改后的问题", confirm=True)
    await h.wait_job(job.id)
    assert (await h.get_job(job.id)).status == "failed"
    assert await h.active_head(case.conversation_id) == old_head
    assert await h.can_search() is False
    await h.reopen()
    await h.retry(job.id)
    assert (await h.get_job(job.id)).status == "succeeded"
    assert await h.note_and_index_match("A.md")
```

夹具生成 change 的路径必须通过真实审批+统一 mutation。运行 `uv run pytest tests/integration/test_recovery_service.py tests/integration/test_recovery_restart.py tests/integration/test_retrieval_service.py -q`。失败注入不能只在 Python 内 catch 后立刻继续，至少覆盖服务重建、PostgreSQL 连接重开和任务读取。

### Task 9（B）：恢复 HTTP、prepared turn 与幂等 SSE

**Create:** `recovery/router.py`、`tests/integration/test_recovery_api.py`。
**Modify:** `chat/router.py/schemas.py`、`conversations/service.py`、`bootstrap/app.py`、`tests/integration/test_app.py`。

- [ ] 四个新恢复路由严格按 §6，same-origin、schema、状态码、preview 过期、内容 hash、CAS、冲突、旧消息不可恢复都测真实应用入口。客户端不能提交 paths 或任意 commit 让服务器照单恢复。
- [ ] `POST recoveries` 持久返回 202 后 worker 认领；worker 不能依赖请求的已关闭 DB session/runtime lease。线程/async task 只负责唤醒，真相是 DB job，重启 GET/重试可继续。
- [ ] prepared_turn `/chat` 唯一 claim：直接使用已准备 user/boundary，不调用 prepare_turn 再增加一条；请求重复返回可识别 already_claimed/run状态，不再运行模型。普通 `/chat` 使用 request_id 去重。
- [ ] SSE user ack/turn complete 附 durable IDs；旧分支/旧 generation 写入与回包拒绝。断流保存 run interrupted 和已有有效 checkpoint，不能把未完成 tool call 当已完成；支持在测试中从中间 checkpoint 安全恢复，不自动重放审批副作用。
- [ ] 成功恢复可独立于重推理：若模型不可用，Job 仍 succeeded、prepared turn 保留，UI 明确“已恢复，生成未开始”。恢复预览/确认不能隐含模型网络调用。

```powershell
uv run pytest tests/integration/test_recovery_api.py tests/integration/test_app.py tests/integration/test_workspace_gate.py -q
```

### Task 10（B）：用户消息编辑、确认弹窗与恢复进度

**Create:** `MessageEditForm.vue`、`frontend/src/features/chat/recovery.ts`、`frontend/tests/unit/chat-recovery.spec.ts`。
**Modify:** `MessageList.vue`、`UserMessageActions.vue`、`chat/store.ts/api.ts`、`AssistantPage.vue`、`shared/api/types.ts`、`tests/fixtures/api.ts`。

- [ ] 先补 API/types fixture，涵盖无文件变化/文件变化/目录变化/冲突/preview 过期/失败重试/成功 prepared turn。
- [ ] `recovery.ts` 显式状态 idle/editing/previewing/confirming/running/failed/succeeded，状态按 conversation_id 存；编辑文本不覆盖服务端历史。函数 beginEdit、cancelEdit、submitEdit、retryRecovery 对 store 公共接口操作，不复制 store 消息真相。
- [ ] 将消息类型与服务端投影转换抽到 `chat/messages.ts`（如 store 继续变大），保留 store facade 导出兼容引用；不要将原 Citation/Draft panel 全量重写。stream handler 和 recovery 共用 generation/owner检查及重载入口。
- [ ] 按 §6.3 绑定按钮、表单、确认、冲突提示；任务首次提交 await 前同步置 busy。被取消 dialog 不请求 start，不改 visibleMessages；请求过期重新预览，不能偷偷沿用旧 confirmed。
- [ ] 恢复成功清理所属会话与受影响路径面板快照、重新拉历史/Library；不擦掉其他会话不相关面板。读取 pending_draft 最新状态，旧 “同意”不可再提交。即使在另一会话看到受影响文件，也失效重读而不是写回旧 buffer。
- [ ] prepared turn 启动新 stream；`send()` 与“提交编辑”共用低层消费 SSE 小接口，但编辑不能先 `messages.splice()` 再调用普通 send；保存后的 UI 以服务端历史为准。
- [ ] 刷新页面/切换会话恢复 job 状态，轮询有退避与销毁处理；失败状态和重试不插入未持久化的 assistant 假消息。

```typescript
it('有文件变化，取消确认不发起回退', async () => {
  const h = await recoveryUiCase({ fileChanges: ['A.md'], confirm: false })
  const before = h.chat.messages.map((message) => message.content)
  await h.editAndSubmit('user-1', '新的问题')
  expect(h.requests('POST', '/conversations/conv-1/recoveries')).toHaveLength(0)
  expect(h.chat.messages.map((message) => message.content)).toEqual(before)
  expect(h.editText()).toBe('新的问题')
})
```

`recoveryUiCase` 在 chat-recovery.spec.ts 实现 routeFetch/confirm 桩和 Pinia，调用真实 store/recovery；不能直接 mock submitEdit 返回预期状态。单测至少涵盖冲突没有 start、确认后顺序、双击一次 start、错误/过期、旧 SSE、切会话、dirty panel、取消、prepared turn 无重复 user、复制不中断编辑。

```powershell
npm --prefix frontend run test:unit -- tests/unit/chat-recovery.spec.ts tests/unit/chat-state.spec.ts tests/unit/message-actions.spec.ts tests/unit/sse.spec.ts
npm --prefix frontend run type-check
```

### Task 11（B）：浏览器端到端与跨模块失败矩阵

**Create:** `frontend/tests/e2e/message-edit-rollback.spec.ts`。
**Modify:** `frontend/tests/e2e/assistant.spec.ts`、`drafts-citations.spec.ts`、`library.spec.ts`；恢复服务集成测试。

使用 E2E fixture route 实际 UI（不可代替真实后端集成），另用应用测试证明同一套 HTTP 与真实 Git/Chroma/checkpointer 的跨模块行为。不得只有 mock UI 成功却没有后端恢复验收。

| 必测场景 | 期望 |
|---|---|
| 每条 user 两个小图标，鼠标/键盘/触屏 | 原文准确复制；编辑理由/禁用状态清楚 |
| 无文件变化的历史编辑 | 新分支仅保留前序历史+新 user+新回答，旧分支仍在库中 |
| 有已执行文件变化 | 弹窗列路径与动作；取消全不变，确认后恢复再生成 |
| 其他会话同路径修改 | 提示冲突，不能确认覆盖，后续正文保持 |
| 其他会话独立文件 | 只修当前会话 A，B 的正文/向量不变 |
| 创建/删除/移动/目录变更 | 恢复存在性/路径/目录，移动两路径索引一致 |
| 摘要压缩后编辑新消息 | 对应历史摘要/工作上下文恢复，UI 全文仍在 |
| Git/文件/索引/候选 checkpoint/发布失败 | 新 head 未误发布，进度持久，重启可继续，成功响应丢失可对账 |
| 弹窗打开后别处修改/切模型 | start 拒绝过期预览，重新预览再确认 |
| 双击、重复 operation_id、重连 | 一次恢复、一条新 user、最多一次 prepared run claim |
| 恢复中跨会话/旧流回包 | 不串消息/草稿，不继续写入旧代数 |
| 普通审批索引失败与重试 | 保留明确已写/索引未同步，检索隔离，不重复追加 |
| 空文件零向量、删除路径无向量 | 不误判未恢复，旧片段不残留 |
| 不可恢复的导入旧消息 | 可展示/复制，编辑禁用并有原因 |
| 旧前端/模型切换/正常 chat | 既有合同仍可用，状态不因 agent 重建丢失 |

```powershell
uv run pytest -q
npm --prefix frontend run type-check
npm --prefix frontend run test:unit
npm --prefix frontend run test:e2e
npm --prefix frontend run build
```

必须实际运行 PostgreSQL/restart/gate 集成测试；环境因测试临时 DB 缺失而 skip 时，阶段不能完成。E2E 使用现有项目标准，不能在用户生产 notes 上做测试。复制安全上下文/权限失败单独验证；不因按钮能点就算完成。

### Task 12：部署、回退迁移策略与文档收尾

**Create:** `docs/04-ops/checkpoint-and-notes-history.md`、`docs/03-modules/chat/message-edit-recovery.md`、results 文件。
**Modify:** `docs/01-architecture/architecture.md/database.md`、`docs/03-modules/chat/context-management.md`、`docs/03-modules/retrieval/retrieval.md`、`docs/02-api/chat-tools.md`、各新增模块 README、`docs/README.md`、plans/README.md、上层 CR/ADR/REQ/API/DATA/TC/OPS 和追溯矩阵。

- [ ] 运维手册写明确启动检查、saver setup、旧数据离线备份/导入/核验、B 根快照能力边界、影子 Git 卷、失败任务查询/重试、阻塞恢复、保留策略。
- [ ] 首版不做自动 checkpoint/Git GC。只保留明确 reachable refs，说明数据增长；以后清理需同时查分支/head/boundary/job 引用，不孤立删除一侧历史。
- [ ] 部署先 A 验收再 B。旧数据导入只导当前真实快照，不能让用户选择旧时点物理文件版本。开编辑入口的条件是 B 完整通过且恢复模块可用，不能只检查有 checkpoint 依赖。
- [ ] 写清版本回退限制：A/B 上线后有新 checkpoint 或正文操作，不能靠切旧代码/旧读表无损回退；需停写、完整备份恢复或验证过的反向数据迁移。保留旧表不是自动双向同步。
- [ ] results 逐任务记录实现/已验证/失败/未运行，给实际两库 commit、命令/环境/测试数/失败注入结果，不抄旧测试数量当新证据。历史评测只新建报告，不改原 run。
- [ ] 根据实际实现更新上层文档独立版本及状态；有真实评审才 approved。代码内写当前已实现部分和限制；未完成项不能标已实现。发布 Notes 只有实际发版才新建，Tag/基线不自动创建。
- [ ] 检查模块依赖、全文搜索新的正式 notes 写入绕过、legacy 消息权威写入、GraphState 序列化和界面 copy/edit accessibility。保留测试临时代码之外不存在第二套 Agent 运行循环。

```powershell
rg -n 'append_message|append_tool_stub|set_pending_draft|apply_compact' src/noteagent
rg -n '\.write\(|\.create\(|\.delete\(|\.move\(' src/noteagent/notes src/noteagent/chat
git diff --check -- . ':(exclude)docs/references' ':(exclude)docs/roadmap'
```

第一条搜索中的剩余调用只能在 legacy 导入/备份读取定义或明确的转换适配中，不能在 checkpoint 模式运行路径。第二条允许低层 repository 实现和统一 mutations，不能 router/drafts 直接副作用；会话 create 等同名方法人工区分，不把所有命中当 bug。

## 8. 交付顺序与 Qoder 执行说明

1. 阅读本计划、CLAUDE.md 和上层依据，记录工作区后 Task 0～4 顺序完成；局部提交仅包含本任务文件，结果在 results 中追加。
2. A 未通过真实持久化/兼容性检查不得继续切换用户运行路径；复制可单独验收，不将编辑 UI 开放给半迁移后端。
3. Task 5～11 逐步实现 Git/统一写入/门禁/纯规划/协调/HTTP/UI/验收。用户已确认冲突拦截与文件确认，本期不得擅自加入“强制回退覆盖他人修改”。
4. 单任务先写测试、运行看实际失败、实现、任务相关检查通过后提交。复杂迁移允许拆更小提交，但不得只改测试期望绕开数据缺失/隔离错误。
5. 完成 Task 12 后给出两个阶段真实验收结果、剩余限制和 diff，不能将本计划复述当执行交付。实际生产数据迁移须明确离线窗口、备份和目标 DB；没有这些条件先完成可审查代码与测试，不在开发测试里修改用户生产数据。

## 9. 计划自检

| 用户要求/风险 | 覆盖位置 |
|---|---|
| 全面迁移，不止换 UI 或删 messages | Tasks 1～3、5～9；A/B 门槛 |
| 状态+历史+摘要+草稿持久化 | §4.1、Tasks 1～3 |
| 影子 Git 不是每消息一个 commit | §5.1、Tasks 5～6 |
| 文件变化撤销与按文件 RAG 修复 | §5.2/5.5、Tasks 7～8 |
| 编辑/复制图标和剪贴板反馈 | §6.3、Tasks 4/10/11 |
| 文件变化弹窗与取消无副作用 | §1.7、§6.3、Tasks 9～11 |
| 冲突拦截且保留后续修改 | §5.2、Tasks 7/9/11 |
| 针对性模块分区/小重构 | §3、Tasks 1/2/6/10 |
| 并发、旧流回包、幂等/重启恢复 | §5.3～5.5、Tasks 6/8/9/11 |
| 旧数据边界、不虚构历史恢复能力 | Task 3、§1.3/§4.1 |
| Docker Git 依赖与历史卷持久化 | Task 5/12 |
| 原评测、旧前端和模型切换兼容 | Tasks 2/3/6/11 |

官方核对资料（核对日 2026-10-01；落地以当前锁定版本实测为准）：

- [LangGraph 持久化/checkpointer](https://docs.langchain.com/oss/python/langgraph/checkpointers)：数据库 saver 与明确 checkpoint config。
- [LangGraph 持久化 memory](https://docs.langchain.com/oss/python/langgraph/add-memory)：生产需要持久 saver，异步 PostgreSQL 用 AsyncPostgresSaver。
- [LangGraph time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)：历史更新创建分支，后续节点重跑，终态不自动执行新一轮。
- [Git commit-tree](https://git-scm.com/docs/git-commit-tree)、[read-tree](https://git-scm.com/docs/git-read-tree)：影子版本对象与独立 index，不使用工程仓库 reset。
- [PostgreSQL advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS)：session lock 支持应用协调，必须由所有入口遵守。
- [Clipboard.writeText](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText)：安全上下文与权限失败处理。
