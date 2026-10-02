# Checkpoint + 影子 Git 两阶段迁移验收记录

验收日期：2026-10-02。代码基线：`59c2321`；被验收 HEAD：`92b0086de29eb5044e552afc1d59e7a24be48200`。

实施依据：[两阶段实施 plan](2026-10-01-checkpoint-shadow-git-rollback.md)。执行方记录：[Qoder 执行结果](2026-10-01-checkpoint-shadow-git-rollback-results.md)。本次只检查代码、执行记录和测试，未修改生产代码。现有未提交的文档目录迁移不计入功能完成度。

## 验收结论

**整体不达标，不能按“两阶段迁移完成”验收。** Task 0、Task 1 基础建设基本落地；Task 2 只完成部分图执行代码，且仍有阻断问题；Task 3～12 未交付。执行结果自身也明确将 Task 2 标记为“进行中”，并未声称整体完成。

| 范围 | 当前状态 | 验收判断 |
|---|---|---|
| Task 0：基线、依赖、测试夹具 | 已交付基础内容，恢复夹具待后续模块落地 | 可作为增量基础接受 |
| Task 1：会话元数据、状态 schema、PostgreSQL saver | 独立状态读写、显式活动 head、持久化测试已交付 | 基础部分基本达标 |
| Task 2：Agent graph | 具备 compact/model/tools/finalize 节点和正常路径测试；正式 ChatAgent/HTTP 未切换 | 部分完成，图核心也需修复下述问题 |
| Task 3～4：旧会话迁移、正式接口切换、消息 ID／复制 | 尚未交付 | 未达标 |
| Task 5～9：影子 Git、统一文件写入、冲突预览、恢复协调、RAG 修复、恢复 API | 尚未交付 | 未达标 |
| Task 10～12：编辑图标、变更确认弹窗、端到端恢复验收、部署与运维 | 尚未交付 | 未达标 |

因此，当前正式聊天仍走旧消息存储和 Agent 循环；尚不能通过新机制完成编辑后重推理、文件回撤和受影响文件的 RAG 重建。`var/notes_history` 还不是已投入运行的影子仓库默认配置。用户要求的复制／编辑、文件变更确认弹窗以及保留他人后续修改的冲突拦截，均不能按已完成计入验收。

## 必须修复的问题

### P1：并发请求会覆盖已接受的用户消息

位置：`src/noteagent/conversations/service.py:235`、`:256`、`:200`。

`prepare_turn` 仅排除相同 request_id，没有会话活动 run 排他、锁定或 head/generation CAS。`publish_head` 无条件更新活动分支和 head。让两个不同 request_id 在同一 head 上并发准备，两个调用均成功返回，但活动 checkpoint 只包含其中一条用户消息。迟到的发布也没有阻止其覆盖较新的 head 或激活旧分支。

补做：明确会话串行策略，以数据库条件更新或锁保护运行认领和发布；旧 run 不得覆盖新 head／generation。增加并发准备、运行期间再次发送和过期发布的回归测试。

### P1：准备过程失败后，请求被永久占用

位置：`src/noteagent/conversations/service.py:256`、`:293`、`:300`。

run 记录先提交，随后才写 checkpoint、发布用户消息和提交消息边界。注入 checkpoint 写失败后，显示历史仍为空，但相同 request_id 重试抛出 `TurnAlreadyClaimed`。另一个故障窗口是 head 已发布、消息边界尚未提交。代码当前没有可继续的准备阶段或补偿处理。

补做：定义持久化的准备阶段与重试／补偿协议；失败必须能判定未接受、可继续或已完成，不能只留下无法重试的 prepared run。覆盖 checkpoint、发布和边界提交各窗口的故障及重启测试。

### P1：checkpoint 草稿仍会被旧表覆盖

位置：`src/noteagent/chat/nodes.py:285`、`:318`，以及 tools 节点的返回状态。

finalize 从旧 `DraftStore` 获取草稿，再写回 checkpoint。将历史草稿只保存在 checkpoint、旧表为空，执行一轮普通问答后，`pending_draft` 由历史草稿变为 null。旧表存在更新草稿时也可能覆盖恢复出的草稿。提案工具的草稿变化还没有作为 tools 节点输出立即持久化。

补做：草稿使用 checkpoint 状态作为来源，明确提案、确认、取消以及恢复后的草稿生命周期；工具节点持久化草稿变化。覆盖历史草稿恢复、旧表残留和工具执行后中断的情况。

### P2：测试夹具掩盖运行状态与 head 问题

位置：`tests/support/harness.py:193`、`:199`。

夹具用 saver 的 latest 执行和发布，而不是严格使用准备出的明确 checkpoint；所有执行均把数据库 run 标记 completed，即使图状态已经 failed。现有 hop-limit 测试仅断言图状态，因此没有验证数据库运行状态一致。

补做：夹具按生产约定传递明确 head，并按实际终态更新 run；同时断言图状态、数据库状态和实际活动 head。

## 仍缺少的 Task 2 验收证据

- 正式 ChatAgent／HTTP／SSE 与评测装配的切换。
- 精确记录每次图运行的 checkpoint 指针，避免 saver latest 进入运行和发布路径。
- 进程中断后运行状态的识别和受控恢复。
- PostgreSQL 上真实图执行的中断、重启及工具消息恢复测试；现有 PostgreSQL 用例主要验证直接状态写入。
- 按 plan 改为异步摘要调用；当前 compact 节点仍同步调用摘要函数。

## 实际验证

在沙箱外重新运行完整后端测试（PostgreSQL 测试使用独立临时 schema）：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --basetemp var/qoder-review-2026-10-02/pytest-elevated-tmp -o cache_dir=var/qoder-review-2026-10-02/pytest-elevated-cache --tb=short
```

结果：**529 passed，1 warning，18.17 秒**。警告来自 Starlette/httpx 依赖弃用。最初两次沙箱运行因验收临时目录及其权限失败，属于验收环境问题，不作为代码缺陷。

另外使用真实 ConversationService、InMemorySaver、SQLite 及现有图夹具执行了三个独立复现。脚本：`var/qoder-review-2026-10-02/repro.py`（本地验收附件，不是生产代码）。

```text
concurrent_prepare: accepted=2, visible_users=["A"]
failed_prepare: retry_rejected=true, visible_messages=0
checkpoint_draft: before={...historical draft...}, after=null
```

测试通过只说明现有覆盖范围内没有回归，不能替代以上并发、故障与恢复要求。

## 交回 Qoder 的执行顺序

1. 先修复上述三个 P1，并补充 P2 对应的夹具与断言；加入能够复现当前失败的回归用例。
2. 完成 Task 2 的正式执行链路和中断恢复约定，与 Task 3 的数据迁移／装配一并验收，避免只有测试夹具在使用图。
3. 按原 plan 完成阶段 A 剩余任务，再推进阶段 B 的统一写入、影子 Git 和逐文件 RAG 修复。
4. 最后验收消息复制／编辑、受影响文件确认弹窗、跨会话／Library 冲突拦截、故障重启，以及部署默认路径。不得以现有 529 项通过作为整体完成证据。
