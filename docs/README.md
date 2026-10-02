# NoteAgent 研发文档

本库描述当前代码与真实执行记录，文档直接原地修改、版本随代码 Tag、历史由 Git 追溯，不设独立文档版本或日常快照。业务目标、需求、目标架构和 CR/ADR 在同级 [NoteAgent-docs](../../NoteAgent-docs/README.md) 维护。

| 用途 | 入口 |
|---|---|
| 入门与开发 | [开发指南](00-overview/README.md) |
| 当前架构与数据库 | [架构目录](01-architecture/README.md) |
| API 与工具契约 | [聊天工具](02-api/chat-tools.md) |
| 模块专题 | [聊天上下文](03-modules/chat/context-management.md)、[前端](03-modules/frontend/frontend.md)、[检索](03-modules/retrieval/retrieval.md) |
| 部署与运维 | [启动教程](04-ops/getting-started.md)、[可观测性](04-ops/observability.md) |
| 执行与历史记录 | [计划和结果](05-records/plans/README.md)、[历史设计](05-records/archive/README.md) |
| 发布记录 | [发布说明规则](06-releases/README.md) |
| 附件 | [历史画布](07-assets/README.md) |

当前会话仍使用自建 Conversation/Message 表和手动压缩，checkpoint 与影子 Git 为 [待评审方案](../../NoteAgent-docs/docs/09-decisions/CR-2026-001-文档治理与整体回退机制迁移.md)，不表示已实现。

evals 的准则、报告和运行数据仍在 [evals](../evals/README.md)，不复制或改写历史指标。个人 [references](references/README.md)、roadmap 目录与根 TODO 保留原位置和内容，作为用户维护的例外，不是正式实现契约。业务术语见 [CONTEXT](../CONTEXT.md)。

代码行为变化时同步实现说明及必要发布记录；需求/目标改变先同步上层 CR 和追溯矩阵。Release Notes 写在 06-releases，只有对外交付才创建明确版本的只读快照。
