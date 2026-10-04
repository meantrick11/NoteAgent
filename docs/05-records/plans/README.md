# 执行计划与结果

本目录保存代码伴随的执行计划和结果，跟随代码版本，无独立文档版本。历史计划中的旧目录与版本操作属于当时的上下文；当前治理以 [文档总目录](../../README.md) 和 [上层规范](../../../../NoteAgent-docs/docs/00-governance/doc-standard.md) 为准。目标需求和架构决策在上层仓库维护。

## 新计划的约定结构

1. **需求 / 设计依据**：引用 [上层文档](../../../../NoteAgent-docs/README.md) 中的设计，或写明经用户确认的简单需求；
2. 目标和范围；
3. 前置条件（当前代码状态、依赖、边界）；
4. 执行步骤（可勾选、可验证）；
5. 验收检查（命令或可判读的结果）；
6. 执行结果和遗留项（回填，不覆盖原步骤）。

不要把“技术方案与关键决策”写成执行计划的权威章节。执行中发现要改变方案，先更新 [上层文档](../../../../NoteAgent-docs/README.md) 的设计并确认，再同步本目录的计划，不在计划内悄悄改决策。

历史计划即使正文含方案与理由，也保持原样；本轮不为对齐新格式而改写它们。本索引在需要时注明“历史格式含设计说明，不作为当前设计主入口”。

## 执行中 / 待执行

| 文件 | 状态 | 说明 |
|---|---|---|
| [2026-10-04-checkpoint-shadow-git-completion.md](2026-10-04-checkpoint-shadow-git-completion.md) | 阶段 A 复验缺陷已修复；B1—B9 已实现（G12／G14／G16 真实演练部分未做） | [执行记录](2026-10-04-checkpoint-shadow-git-completion-results.md)；[第二轮验收](2026-10-04-checkpoint-shadow-git-completion-review-round2.md)；[修复与验证](2026-10-04-checkpoint-shadow-git-completion-fixes.md)：A 修复已合并基础。B1—B8 提交见 results 表，G01—G16 逐条状态在 results 末尾；后端 600+、前端 139 单测 / 59 e2e 及构建通过 |
| [2026-10-01-checkpoint-shadow-git-rollback.md](2026-10-01-checkpoint-shadow-git-rollback.md) | 部分完成，剩余执行见 2026-10-04 计划 | 原始两阶段范围与接口合同；基础及验收修复已合并，正式聊天切换与影子 Git 等尚未完成，不能视为整体已验收 |
| [2026-09-10-learning-note-quality.md](2026-09-10-learning-note-quality.md) | 部分完成（持续） | 学习型笔记 v0.2 准则、语义 Judge、Prompt 迭代留痕已交付；l01 的加工维度仍未达合格线（现行 prompt 见 [note-quality.md](../../../evals/criteria/note-quality.md)） |

V2.7 前端初始化计划的实现部分已完成（见下方"已完成"表），Tasks 1–8 逐项有验证证据。
V2.2／V2.3 仍按当前可用处理，其余 V2 迭代在前端扩容后继续——前端扩容不等于 V2 整体验收通过。

## 已完成或部分完成

| 文件 | 状态 | 验证入口 |
|---|---|---|
| [2026-10-01-docs-v1.5.1-finalization.md](2026-10-01-docs-v1.5.1-finalization.md) | 已完成 | 执行记录见 [results](2026-10-01-docs-v1.5.1-finalization-results.md)：入口、链接与保护核对通过；本地基线提交 `dd23d88` 与标签 `docs-v1.5.1` 已建立，未推送远程 |
| [2026-09-28-settings-navigation-and-sections.md](2026-09-28-settings-navigation-and-sections.md) | 已完成 | 执行记录见 [results](2026-09-28-settings-navigation-and-sections-results.md)：顶部四工作入口＋齿轮、设置两分类；test:unit 120 / test:e2e 54 / build 通过 |
| [2026-09-28-vue-frontend-initialization.md](2026-09-28-vue-frontend-initialization.md) | 已完成（实现部分；文档同步见结果文档 §未运行项） | 执行记录见 [results](2026-09-28-vue-frontend-initialization-results.md)：F01–F16 逐项证据、test:unit 114 / test:e2e 46 / pytest 502 |
| [2026-09-27-docs-four-directory-consolidation.md](2026-09-27-docs-four-directory-consolidation.md) | 已完成 | 执行记录见 [2026-09-27-docs-four-directory-consolidation-results.md](2026-09-27-docs-four-directory-consolidation-results.md) |
| [2026-09-27-docs-four-directory-consolidation-results.md](2026-09-27-docs-four-directory-consolidation-results.md) | 整理记录（不是实现任务） | 基线、迁移映射、保护比对与链接验证 |
| [2026-09-27-documentation-reorganization.md](2026-09-27-documentation-reorganization.md) | 已完成（目录规则已由四目录整理调整） | 执行记录见 [2026-09-27-documentation-audit.md](2026-09-27-documentation-audit.md)；当时范围与结论未改 |
| [2026-09-27-documentation-audit.md](2026-09-27-documentation-audit.md) | 整理记录（不是实现任务） | 基线、清单、冲突矩阵、验证结果 |
| [2026-09-26-v1-acceptance.md](2026-09-26-v1-acceptance.md) | 已完成 | [v1-acceptance-report.md](../../../evals/reports/v1-acceptance-report.md)；V1 已验收，tag `v1.0.0` |
| [2026-09-26-chat-draft-in-citation-pane.md](2026-09-26-chat-draft-in-citation-pane.md) | 已完成 | 计划 §执行结果摘要（2026-09-26 回填） |
| [2026-09-26-chat-layout-resize-and-draft-actions.md](2026-09-26-chat-layout-resize-and-draft-actions.md) | 已完成 | 计划 §执行结果摘要；界面现状见 [frontend.md](../../03-modules/frontend/frontend.md) §3.1 |
| [2026-09-25-rag-quality-improvement.md](2026-09-25-rag-quality-improvement.md) | 已完成（任务 5 未做，8.4–8.6 按停止条件跳过） | [rag-v1-report.md](../../../evals/reports/rag-v1-report.md) |
| [2026-09-25-model-switching-reliability.md](2026-09-25-model-switching-reliability.md) | 已完成（1 项部分：双击发送缺前端自动化回归） | 计划 §9 执行结果（2026-09-26），含未完成项与运维迁移说明 |
| [2026-09-25-model-switching-ui.md](2026-09-25-model-switching-ui.md) | 已完成 | 计划 §9 执行结果（2026-09-25） |
| [2026-08-26-context-management.md](2026-08-26-context-management.md) | 已实现（原规格未回勾） | [context-management.md](../../03-modules/chat/context-management.md)、[database.md](../../01-architecture/database.md) |
| [2026-08-20-chat-history-persistence.md](2026-08-20-chat-history-persistence.md) | 已实现（原规格未回勾） | [database.md](../../01-architecture/database.md) |
| [2026-08-20-conversation-rename-delete.md](2026-08-20-conversation-rename-delete.md) | 已实现（原规格未回勾） | PATCH / DELETE `/conversations/{id}`，见 [architecture.md](../../01-architecture/architecture.md) §5.2.1 |
| [2026-09-05-documents-panel.md](2026-09-05-documents-panel.md) | 已实现 | [frontend.md](../../03-modules/frontend/frontend.md) §4–5 |
| [2026-09-02-auto-index-on-approve.md](2026-09-02-auto-index-on-approve.md) | 已实现 | [retrieval.md](../../03-modules/retrieval/retrieval.md) |
| [2026-09-06-prompt-eval.md](2026-09-06-prompt-eval.md) | 已实现 | [evaluations/README.md](../../../evals/README.md) |
| [2026-09-06-readme-homepage.md](2026-09-06-readme-homepage.md)、[2026-09-06-readme-tutorials.md](2026-09-06-readme-tutorials.md) | 已实现 | 根 [README.md](../../../README.md)、[tutorials/](../../00-overview/README.md) |
| [2026-09-07-chat-citations.md](2026-09-07-chat-citations.md)、[2026-09-07-chat-cite-edit.md](2026-09-07-chat-cite-edit.md) | 已实现 | [frontend.md](../../03-modules/frontend/frontend.md) §3；`messages.citations` 见 [database.md](../../01-architecture/database.md) §3.2 |
| 过程排系列：[2026-09-09-pending-draft.md](2026-09-09-pending-draft.md)、[2026-09-09-cite-pane-isolation.md](2026-09-09-cite-pane-isolation.md)、[2026-09-09-chat-trace-cursor-flow.md](2026-09-09-chat-trace-cursor-flow.md)、[2026-09-10-chat-trace-tense.md](2026-09-10-chat-trace-tense.md) | 已实现，后序计划取代前序口径 | [frontend.md](../../03-modules/frontend/frontend.md) §3；时态与标题以最后一份为准 |

## 历史参考

| 文件 | 说明 |
|---|---|
| [2026-09-09-chat-trace-summary.md](2026-09-09-chat-trace-summary.md) | 明确被 [2026-09-09-chat-trace-cursor-flow.md](2026-09-09-chat-trace-cursor-flow.md) 取代（英文汇总、live 可展开、Thinking 正文） |
| [2026-09-09-chat-stream-trace.md](2026-09-09-chat-stream-trace.md) | 真流式 token 的原始规格；过程排后续细节见后续计划 |
| [draft-generation.md](draft-generation.md) | **已归档**：正文在 [archive/designs/ingestion-job-early-design.md](../archive/designs/ingestion-job-early-design.md)，本路径只留跳转页。入库 Job / URL 源 / 自动索引设想，不是现行架构 |

## 维护动作

- 行为变更后同步 [当前架构](../../01-architecture/README.md)；执行后同步本索引状态与验证入口。
- 达到退出标准才改 [当前版本路线](../../../../NoteAgent-docs/docs/02-requirements/REQ-CATALOG-产品能力与验收要求.md)；替代旧设计必须两端加替代关系。
- 单个事实只保留一个主要维护位置，其他文档链接过去，不复制。


本次迁移见 [双仓库迁移记录](2026-10-01-two-repository-document-migration.md)。
