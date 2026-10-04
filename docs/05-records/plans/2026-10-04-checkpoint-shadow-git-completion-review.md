# Qoder 阶段 A 执行结果验收

日期：2026-10-04。比较基线：`333280a...14b93d0`。分支：`codex/checkpoint-shadow-git-completion`。

依据：[完成计划](2026-10-04-checkpoint-shadow-git-completion.md)、[Qoder 执行结果](2026-10-04-checkpoint-shadow-git-completion-results.md)。

**结论：正式聊天已接入 checkpoint，旧会话导入和消息复制已有实现；阶段 A 仍存在阻塞缺陷，暂不通过。B1—B9 未执行，整体回退需求未完成。**

本记录不修改 Qoder 的历史报告、不实施代码修复、不合并或推送分支。测试和复现使用隔离 schema／临时笔记／SQLite／InMemorySaver，未回退真实用户笔记。

## 已核实的交付与测试

- 实际提交存在：A1 `deab0a7`、A2 `730ac9f`、A3 `fe44f3c`、结果记录 `14b93d0`。
- 正式 `/chat` 通过 Agent facade 执行图；正式会话消息和草稿能够从活动 checkpoint 投影；迁移 CLI 和原文复制入口已存在。
- 本轮重跑后端专项：29 passed；全量 `tests/unit tests/integration`：559 passed，1 条既有 Starlette/httpx 弃用提示，37.81 秒。
- 前端专项单测：10 passed；全量单测：130 passed；`npm run build` 通过。
- 本轮专项 E2E：`npm run test:e2e -- tests/e2e/checkpoint-chat.spec.ts` → 2 passed（12.1 秒），验证原文复制及编辑按钮禁用。
- Qoder 报告的全量 E2E 56 passed 尚未由本轮全量重跑确认，不能混写为本轮验证结果。

## Standards：执行隔离与模块合同

### S1 [P1] 草稿变更绕过活动运行 claim，破坏回复发布

位置：[conversations/service.py:246](../../../src/noteagent/conversations/service.py:246)，`clear_pending_draft` 有相同路径。

`update_pending_draft` 直接发布新 checkpoint，没有检查该会话 prepared/running/interrupted run。模型 runtime 的 chat/write lease 只统计维护窗口，不互斥会话草稿和聊天。

隔离复现：保存待审草稿→prepare_turn 接收新问题→update_pending_draft→执行准备好的 Agent。运行抛出 StaleConversation，活动历史包含用户问题但缺少生成的助手消息。

违反完成计划 A2 的运行租约／候选隔离要求及 G03。修复应在服务层对草稿变更和 run claim 统一加锁／校验；不能只禁用当前页面按钮。批准写正文之前也必须验证该权限。

## Spec：A 阶段要求

### R1 [P1] 草稿 CAS 使用重新读取的 head，可能覆盖新状态

位置：[conversations/service.py:275](../../../src/noteagent/conversations/service.py:275)、[write_state:150](../../../src/noteagent/conversations/service.py:150)。

草稿从旧 view 构造完整状态，write_state 却重新读取最新 head 作为 CAS expected，而不是使用该 view 的 checkpoint ID。

隔离复现：读取旧 view→另一操作发布新 summary→从旧 view 发布草稿编辑。实际保存成功，新 summary 被旧值覆盖。返回结果为 stale_cas_rejected=False、new_state_preserved=False。

违反 A2 草稿 CAS 要求。必须按实际读取的 branch/head/generation 发布；旧 view 应被拒绝，不能“刷新预期值”后覆盖。增加穿插执行的丢更新测试，断言完整新状态保留。

### R2 [P1] 正式 HTTP 缺少中断运行续接

位置：[chat/agent.py:69](../../../src/noteagent/chat/agent.py:69)、[conversations/service.py:316](../../../src/noteagent/conversations/service.py:316)、chat/router.py、chat/schemas.py。

服务层有 resume_turn，execute_turn 支持 resume，但正式 HTTP 没有对应调用，Agent.run 固定使用默认 resume=False。interrupted run 仍阻止新 prepare；同 request_id 重试也被拒绝。

本轮实际通过真实测试 App 复现：prepare 后 interrupt，随后 POST /chat 返回 409，detail="conversation has a running turn"；没有 resume 路由。没有启动或访问真实笔记目录。

违反 A2“重连按明确 run_id 恢复”。需将续接接入正式接口／Agent facade，校验会话归属及 lease，详情提供恢复位置；客户端刷新或重连可接续，不重复接受用户消息。补正式 HTTP 中断→续接→完成测试，不能只保留服务层测试。

### R3 [P2] generation 被当成草稿版本，旧标签页审批校验无效

位置：[chat/agent.py:149](../../../src/noteagent/chat/agent.py:149)、[conversations/service.py:265](../../../src/noteagent/conversations/service.py:265)、[frontend api.ts:44](../../../frontend/src/features/chat/api.ts:44)。

expected_revision 与 generation 比较，同分支聊天和草稿编辑并不递增 generation；前端保存／审批也没有传递实际草稿版本。当前测试仅提交人为数值99，无法证明真实旧标签页被拒绝。

违反 A2 stale-review 及 A3 state_revision 合同。保持 generation 的分支隔离语义，另使用真实 head revision／checkpoint ID及 draft 身份，读取、SSE和前端保存／审批合同一致。补两个标签页先后读取／编辑／审批的真实过期测试。

## 关联风险与继续顺序

chat/agent.py 当前批准正文后才清 checkpoint 草稿，若 CAS 或 saver 失败，正文已改变，索引更新未执行；重试 append 还可能重复写。B3/B4 的持久 mutation、幂等与索引维修必须覆盖它，不能将当前批准路径称为完整恢复保障。

1. 先修 S1、R1、R2、R3，各补真实失败测试，修复后重跑 A 验收。
2. 然后按原完成计划 B1→B9 继续：门禁台账、影子 Git、统一写入、可靠 RAG、预览冲突、恢复协调、API、编辑 UI、部署与全链路验收。
3. 所有 G01—G16 有真实证据后才宣布整体完成。559 项旧／当前测试通过不替代缺失场景。

本轮两轴结果：Standards 1 项 P1；Spec 2 项 P1、1 项 P2。B 的未实施属于报告已承认的剩余范围，不重复计为 A 新缺陷。
