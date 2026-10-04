# 阶段 A 第二轮验收缺陷修复

日期：2026-10-04。依据：[第二轮验收](2026-10-04-checkpoint-shadow-git-completion-review-round2.md)。本轮修复 S2、R4、R5、R6，不代表整体回退迁移完成。

## 修复结果

| 问题 | 当前行为 | 回归证据 |
|---|---|---|
| S2：审批被拒绝但笔记已写入 | Conversation 行锁覆盖运行占用、revision 校验、读取 checkpoint、候选保存和正文写入。认领及发布使用同一非阻塞行锁；被占用、过期版本或 saver 失败均在写文件之前拒绝 | `test_busy_approval_has_no_file_or_draft_side_effect`；`test_review_holds_postgres_permission_during_saver_await`；`test_review_saver_failure_does_not_invoke_writer` |
| R4：正式页面缺续接入口 | 详情返回 interrupted 时显示“继续生成”；用户点击后发送 run_id，不重复接受用户消息。运行中禁止新问题，续接结束重新加载正式 checkpoint 消息 | `checkpoint-resume-real.spec.ts` 通过隔离真实 HTTP 后端验证刷新、点击、再次刷新，仅一条用户消息与一条助手回复 |
| R5：错误会话续接改变运行状态 | 认领前验证 run 所属会话和 expected_revision，错误会话、过期版本不会取得运行租约 | `test_checkpoint_chat_api.py` 的对应 HTTP 回归 |
| R6：dirty 草稿借用新版本覆盖新内容 | 每个会话面板独立保存 draftRevision，绑定正在编辑的正文。刷新、切会话、draft SSE 均保留 dirty 正文及原版本；保存与审批携带该版本 | `chat-state.spec.ts` 的 stale draft 与 draft SSE 回归 |

复核时同时修复：过期租约可在运行期间的详情刷新中协调为 interrupted；晚到的审批响应只更新原会话；旧会话 SSE 不抢占新选择；异步审批持锁时重命名、删除在工作线程执行，避免阻塞事件循环。无待审草稿时拒绝仍保持幂等成功。

## 验证

- 后端 `pytest tests/unit tests/integration -q --tb=short`：570 passed。
- 前端 `npm run test:unit`：135 passed。
- 前端 `npm run test:e2e`：57 passed，包含真实 HTTP 续接测试。
- 前端 `npm run build`：通过。
- 规范及需求复核：未遗留明确 P1/P2；结论仅覆盖本轮阶段 A 修复。

完整浏览器回归首次运行中，隔离后端冷启动超过 25 秒；调整该测试的启动等待至 55 秒并收集 stderr，完整重跑通过。生产逻辑不依赖这个测试等待时间。

## 尚未完成

B1—B9 仍待执行，包括影子 Git、初始笔记版本、全部写入的持久 mutation、按文件 RAG 修复、冲突检测、恢复状态机、API 和用户消息编辑确认 UI。

本轮先保存未发布 checkpoint 候选，再写正文，可避免 saver 写入失败时修改文件；如果正文写入后，业务数据库最终提交失败，仍需要 B3/B4 的持久日志、幂等恢复和索引维修。当前成功审批仍按原流程更新索引，尚无完整的崩溃补偿。不能把本轮修复当作文件和 RAG 回退已验收。
