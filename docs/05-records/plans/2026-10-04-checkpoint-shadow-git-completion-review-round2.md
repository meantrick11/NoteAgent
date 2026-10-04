# Qoder 阶段 A 修复复验（第二轮）

日期：2026-10-04；基线 `14b93d0...7259b71`；修复提交 `c754c66`；结果回填 `7259b71`。

依据：[完成计划](2026-10-04-checkpoint-shadow-git-completion.md)、[第一轮验收](2026-10-04-checkpoint-shadow-git-completion-review.md)、[执行结果](2026-10-04-checkpoint-shadow-git-completion-results.md)。

**结论：R1 原始丢更新问题已修复；后端已具备单调 revision 和 HTTP 续接。但是草稿批准的占用检查仍晚于正文写入，前端未接入续接，另有续接拒绝的副作用和旧编辑 revision 错配。阶段 A 暂不通过。B1—B9 尚未开始，不能直接宣称进入 B2。**

## 本轮验证

- `.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --tb=short`：**563 passed**，40.50 秒，1 条既有 Starlette/httpx 弃用提示。
- frontend：`npm run test:unit` **130 passed**；`npm run test:e2e` **56 passed**（17.0 秒）；`npm run build` 通过。
- 隔离临时笔记目录、SQLite、InMemorySaver、真实 FastAPI 路由／ConversationService，复现两个未覆盖的拒绝请求副作用。没有修改真实笔记或应用数据库。
- Alembic 新增 `d4a7e1b90c22` 的列定义已检查；Qoder 报告临时 schema upgrade/downgrade/upgrade 通过，本轮未另行重复该演练。
- 当前 E2E 大多拦截 API，未覆盖真实后端中断→页面续接或并发草稿审批，不能证明这些场景完成。

## 已改善的部分

1. 草稿候选使用读取时的 exact checkpoint ID、generation 和 revision 做 CAS，不再以刷新后的 head 授权旧状态发布。
2. 草稿保存／清除增加 active-run 检查，已占用时拒绝发布新 head；修复原有“保存草稿直接使活动回复发布失效”的已复现场景。
3. 新增 conversations.revision，每次发布 head 自增；正常草稿保存／审批请求由前端携带 expected_revision。
4. POST /chat 可以用 run_id 续接，详情返回 active_run，后端测试覆盖不重复接受用户消息的正常续接路径。

## Standards：执行隔离

### S2 [P1] 批准／覆盖草稿仍先写正文，随后才因运行占用拒绝

位置：[chat/agent.py:176](../../../src/noteagent/chat/agent.py:176)、[chat/agent.py:187](../../../src/noteagent/chat/agent.py:187)。

正文 `_write_draft` 在 clear_pending_draft 的运行占用检查前执行。运行占用时审批返回409，正文却已经写入，草稿仍存在；索引同步在清草稿之后，因此没有执行。

实际 HTTP 复现：给 A 写入 checkpoint 待审草稿→prepare_turn 接收新问题→携带当前 revision POST /chat/review approve。输出：`approval_status=409`，`note_written_despite_busy=true`。

这不是只有 saver/DB 故障才发生的 B 阶段风险，而是正常忙状态拒绝就有副作用，仍不满足第一轮 S1。正式正文写入前需要在服务层取得并维持排他操作权，同时校验 draft 身份与 revision；不能只在写后检查或只在 UI 禁用。完整跨存储幂等仍由 B3/B4 补齐。

## Spec：正式恢复与版本合同

### R4 [P1] 前端没有接入新增的中断续接能力

位置：[frontend api.ts:57](../../../frontend/src/features/chat/api.ts:57)、[store.ts:279](../../../frontend/src/features/chat/store.ts:279)。

新增的 active_run 只有类型定义；store 不消费它，API 请求仍只发送新 question/conversation_id/request_id，没有 run_id 续接方法和页面操作。中断后用户刷新／重开会话，新问题仍被 interrupted run 阻挡。

按 A2/G03 补详情加载后的运行状态、明确的“继续生成”操作、run_id 请求、忙态及旧响应隔离。不能在页面加载时静默调用模型。必须增加真实后端的页面断流／重启→主动续接测试；手工 POST /chat 的后端测试不替代产品链路。

### R5 [P2] 错误会话的续接请求返回404，却先占用了原运行

位置：[router.py:229](../../../src/noteagent/chat/router.py:229)、[router.py:238](../../../src/noteagent/chat/router.py:238)。

先 agent.resume(run_id)，认领事务已提交 running＋新 lease，之后才验证 requested conversation。实际 HTTP 复现：A interrupted run 使用 B conversation_id 请求→404，但 A run 变为 running；正确请求暂时不能再续接，必须等待租约过期。

输出：`wrong_conversation_resume_status=404`，`actual_run_status_after_rejection="running"`。应在同一认领事务内先校验会话归属，再修改状态；404/409拒绝必须零副作用。补跨会话、失效 revision、重复续接的正式路由测试。

### R6 [P2] dirty 草稿保留旧编辑文本，却领取了新 revision

位置：[store.ts:284](../../../frontend/src/features/chat/store.ts:284)、[store.ts:355](../../../frontend/src/features/chat/store.ts:355)、[store.ts:507](../../../frontend/src/features/chat/store.ts:507)。

场景：A 标签页保留本地草稿编辑并切到其他会话；B 修改同一草稿；A 返回。applyServerDraft 保留 A 的 dirty 旧文本，loadMessages 却将全局 stateRevision 更新为 B 的新值。A 保存时用新 token 发送旧文本，后端 CAS 可以通过，覆盖 B。

编辑缓冲必须绑定该会话／该 draft 的原始 revision；刷新不自动更新 dirty 文本的写入权限。revision 应随 panel 保存，服务端有新状态时提示冲突并保留本地文本；不能仅维护一个全局 revision。补两标签页＋切换会话＋dirty 缓冲测试。

## 后续执行顺序与验收

1. 修复 S2、R4、R5、R6，新增当前失败场景测试，再验收 A；现有通过项无需重写。
2. 按完成计划先 **B1 工作区门禁与持久台账**，再 **B2 影子 Git**，随后 B3—B9。当前源码没有 recovery 模块、版本服务或相关 B1 台账实现，不能跳过 B1。
3. 持久 mutation／索引修复仍须覆盖批准正文后 DB/saver 失败、重复 append 等已知风险。全部 G01—G16 有实际证据后才整体验收和准备合并。

两轴结果：Standards 1 项 P1；Spec 1 项 P1、2 项 P2。本轮只核查与记录，没有修改业务代码、合并或推送。
