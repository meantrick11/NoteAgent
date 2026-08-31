# plans

给实现 Agent 按任务执行的规格。产品边界以 [../architecture/draft-generation.md](../architecture/draft-generation.md) 为准；短期记忆以 [../architecture/context-management.md](../architecture/context-management.md) 为准。冲突时：已落地步骤以本目录为准去改代码，未做的目标以 architecture 为准。

## 文件

| 文件 | 说明 |
|------|------|
| [2026-08-20-chat-history-persistence.md](./2026-08-20-chat-history-persistence.md) | 会话列表 + PostgreSQL 消息落库（展示层，已做） |
| [2026-08-20-conversation-rename-delete.md](./2026-08-20-conversation-rename-delete.md) | 侧栏重命名、删除（已做） |
| [2026-08-26-context-management.md](./2026-08-26-context-management.md) | 短期记忆实现规格（Turn / stub / watermark / 环境配置压缩）。**已实现。** 表结构对照 [../architecture/database.md](../architecture/database.md)。生产库须 `alembic upgrade head` 到 `3d1c2b8a9e4f`。 |
