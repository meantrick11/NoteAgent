# 阶段 B 独立验收

日期：2026-10-04。范围：`git diff c733da9...3e77ae6`（B1—B9）。依据：[完成计划](2026-10-04-checkpoint-shadow-git-completion.md)，特别是 B3—B8 和 G07—G15。

**结论：未达标，不建议合并。** 实施代码已经提交，但多项关键安全条件未接入正式链路或在故障／并发时失效。问题不限于执行报告承认的三项现场演练／文档欠缺。本轮只验收，未修改实现。

## 独立验证

| 项目 | 结果 |
|---|---|
| 后端 `pytest tests/unit tests/integration -q --tb=short` | 615 passed, 1 skipped |
| 前端 `npm run test:unit` | 139 passed |
| 前端 `npm run test:e2e` | 59 passed |
| 前端 `npm run build` | 通过 |

以上与 Qoder 报告一致，但现有测试未覆盖下面的正式接线和失败路径。另使用临时目录、真实影子 Git／隔离 SQLite 与内存 saver 复现缺陷，不接触用户 notes。

## Standards：实现可靠性

本节聚焦明确的接线、时序与持久化缺陷，不把代码气味当成阻塞依据。

| ID | 优先级 | 位置 | 缺陷与触发 | 修复要求 |
|---|---|---|---|---|
| S-B01 | P1 | `model_management/service.py:472`；`notes/router.py:307` | chat 仍只使用进程内 runtime 计数；notes 读取也未使用工作区门禁。恢复或持久 maintenance 期间其他聊天／读取不受 WorkspaceGate 阻断，可读取中间正文 | 在正式请求入口接入跨进程门禁，保持规定锁顺序；状态／维修入口按合同例外放行 |
| S-B02 | P1 | `chat/tools.py:65`；`retrieval/repairs.py:128` | 检索仍调用 `retrieval.search`，`search_synced` 无正式调用；启动 reconciliation 也无调用。failed/pending 文件旧向量仍可进入 Agent 上下文 | 接入检索过滤／不可用结果及启动维修，补正式 HTTP／工具链回归 |
| S-B03 | P1 | `notes/mutations.py:367` | Git 失败后的 `_restore` 只写回原来存在的文件。故障注入确认 CREATE 后新增文件残留；MOVE A→B 后 A、B 都存在 | before-image 必须表达不存在、文件和目录；精确撤销新增／移动／重命名，补偿失败保持维修阻断 |
| S-B04 | P1 | `notes/mutations.py:160` | retained ref 只在台账不存在时续办，但正常流程先创建 writing 台账。Git 成功后 DB 台账更新失败，再用同 operation_id 重试，会再次执行 append。已隔离复现重复追加 | 对已有 writing／failed 台账恢复 retained commit，幂等提交台账及 seq，不重放正文 |
| S-B05 | P1 | `bootstrap/app.py:108`；`chat/agent.py:207`；`notes/router.py:144` | Git 不可用时生产容器设 mutations=None，后续进入“测试兼容”直接写盘分支，绕过历史与台账 | 区分测试容器和生产降级；生产历史不可用必须拒绝正式写入 |
| S-B06 | P1 | `recovery/router.py:90` | 先执行 start 产生文件／head 副作用，之后才核对 URL 会话。把 A 的 preview 发到 B URL，会先回退 A 再返回 404 | 在任何副作用之前验证 preview／operation 与会话归属 |
| S-B07 | P2 | `frontend/src/features/chat/store.ts:916`、`:964` | preview/job 为全局状态，确认和 prepared-turn 从 currentId 取 owner。预览期间切到 B，A 的晚到结果可挂到 B，后续续接也可归属错误 | 按 conversation／branch／请求 token 隔离异步结果，续接绑定 job 所属会话 |
| S-B08 | P1 | `notes/mutations.py:151`、`:172` | before bytes、expected hash、parent commit 在独占锁之前读取；校验后另一个进程写入，就会用过期 before-image 执行和补偿 | 锁内读取、校验、写台账、写文件与发布；锁外只做无状态格式校验 |

## Spec：需求符合性

| ID | 优先级 | 位置 | 缺陷与证据 | 对应计划 |
|---|---|---|---|---|
| R-B01 | P1 | `recovery/service.py:175`、`:250` | start 校验 conversation revision，却不在独占锁内重验 workspace_seq、当前 hash、后来来源及冲突。隔离复现：preview 后 Library 更新 A，确认旧 preview 仍 succeeded 并删除新版 A | B6 必须在独占门禁内重验 seq/head/hash/冲突；G09 保留共享后续修改 |
| R-B02 | P1 | `recovery/service.py:264`、`:275` | repair_many 返回 failed，协调器不检查仍发布成功并解除 maintenance。隔离复现 vector delete 抛异常，index_repairs=failed，但 job=succeeded、maintenance=None | B6 索引一致后才发布；G07、G12 维修阻断 |
| R-B03 | P1 | `conversations/service.py:326`；`recovery/service.py:269` | candidate_saved 后故障，retry 再次 fork 同 request_id，直接 TurnAlreadyClaimed，不能续办已保存候选。故障注入复现，maintenance 保留且普通重试无法完成 | B6 同计划幂等重试；G12 候选保存／发布前故障恢复 |
| R-B04 | P1 | `chat/router.py:113` | 正式消息接口仍统一 `editable=False`，B8 编辑图标实际仍不能点击。新增 UI 的 mock 测试未发现此问题 | B7 返回真实安全边界能力；B8 编辑入口；G15 正式 UI |
| R-B05 | P1 | `conversations/service.py:301`、`:790`；`recovery/service.py:341` | 恢复 fork 没有创建 UserMessageBoundary，且候选 UI 用户消息 ID 与 run.user_message_id 分别生成。恢复后重推理中断，resume 要求该边界，无法通过；新消息也缺安全回退边界 | B7 prepared-turn 及中断续接保持正式合同；G03、G13 |
| R-B06 | P1 | `conversations/service.py:367`、`:435` | 恢复 run 保存旧 generation，发布却将会话 generation 加一。隔离实测 claim_prepared 后 run=0、conversation=1，finish_run 立即 StaleConversation，重新生成结果无法正式持久化 | B7 重新生成合同；G13 prepared-turn 可完成且不重复接受消息 |
| R-B07 | P2 | `recovery/service.py:349` | 恢复将 working_records 换成完整 ui_messages，并无条件清空边界 pending_draft；没有忠实恢复边界已有的压缩工作状态及草稿 | B6 保留摘要、草稿和工作上下文；G11 无文件改动的状态回退 |

### 隔离复现步骤

- R-B01：使用 `test_recovery_coordinator._Env`，创建 turn、owned A，生成 preview，再经 `Origin.library()` 替换 A，最后 start 原 preview。当前结果 succeeded，A 被删除；正确结果应冲突且新版正文保留。
- R-B02：同环境生成含 A 的 preview，令 retrieval.delete_note 抛异常，再 start。当前 failed repair 未阻止 succeeded 和 maintenance 清除。
- R-B03：注入 `candidate_saved`，首次 start 失败；retry 同 job，当前报 TurnAlreadyClaimed。
- R-B06：成功 start 后 claim_prepared，再用其 checkpoint 调用 finish_run，当前 generation 不匹配而报 StaleConversation。
- S-B03：真实影子 Git 的 snapshot 注入失败，分别执行 CREATE 和 MOVE，检查磁盘残留。
- S-B04：Git 已提交后令 `_ledger_status(applied)` 失败，再用同 operation_id 重试 append，检查正文出现两份追加。

## 仍未完成的验收项

G12 真实停止／重启演练、G14 双进程争抢演练，以及 G16 上层文档同步仍欠缺。上层仓库实际存在于 `D:/develop/project/selfproject/agentbuild/NoteAgent-docs`，不能以环境没有仓库为由判定无法执行。

应先修上述缺陷，补能覆盖正式接线的回归，然后执行演练和文档同步，再重新评价 G01—G16。当前结果表中对应 G07、G09、G12—G15 的“通过／部分”不能作为整体合并依据。

统计：Standards 8 项（7 P1、1 P2），最严重为门禁及幂等写入失效；Spec 7 项（6 P1、1 P2），最严重为共享修改被过期预览覆盖及重推理无法提交。
