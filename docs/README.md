# docs

按阅读顺序串联。实现时：源码旁 README 描述**现状**；`architecture/` 里带「目标」字样的章节不要当成已经上线。

不要写密钥，不要放 `var/` 运行时数据。

## 阅读顺序

1. **[architecture/DESIGN.md](architecture/DESIGN.md)** — 最早的屏幕/音频设计。**不要按它写代码。**
2. **[architecture/architecture.md](architecture/architecture.md)** — **现行项目架构书**（4.1 前端，4.2 后端含路由/Agent，4.3 数据库，4.4 笔记）。
3. **[architecture/chat-tools.md](architecture/chat-tools.md)** — Agent 四工具契约（工作流、参数、人审；已落地）。
4. **[architecture/database.md](architecture/database.md)** — PostgreSQL 两表 + 上下文列、Store、Alembic head。
5. **[architecture/draft-generation.md](architecture/draft-generation.md)** — 笔记草稿目标工作流；Job/自动索引尚未做。
6. **[architecture/context-management.md](architecture/context-management.md)** — 短期记忆契约（已按本文改代码：Turn、stub、watermark、压缩）。
7. **[plans/](plans/README.md)** — 已做过的实现切片。
8. **[evals/](../evals/README.md)** — 提示词黄金集与人工评分（不进 pytest）。
9. **`src/noteagent/**/README.md`** — 与代码同步的现状说明。

## 目录

| 目录 | 里面有什么 |
|------|------------|
| [architecture/](architecture/README.md) | [架构书](architecture/architecture.md)、[聊天工具](architecture/chat-tools.md)、[数据库](architecture/database.md)、DESIGN（历史）、草稿生成、短期记忆、画布 |
| [design/](design/README.md) | 子系统设计文档索引 |
| [plans/](plans/README.md) | 已落地的实现规格 |
| [decisions/](decisions/README.md) | ADR，目前可空 |
| [evaluations/](evaluations/README.md) | 指针：黄金集在仓库根 [evals/](../evals/README.md) |
| [references/](references/README.md) | 外部摘录，不是契约 |
