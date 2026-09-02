# plans

给实现 Agent 按任务执行的规格。现行系统以 [../architecture/architecture.md](../architecture/architecture.md) 为准。上下文公式以 [../architecture/context-management.md](../architecture/context-management.md) 为准。

## 文件

| 文件 | 说明 |
|------|------|
| [2026-08-20-chat-history-persistence.md](./2026-08-20-chat-history-persistence.md) | 会话列表 + PostgreSQL 消息落库（已做） |
| [2026-08-20-conversation-rename-delete.md](./2026-08-20-conversation-rename-delete.md) | 侧栏重命名、删除（已做） |
| [2026-08-26-context-management.md](./2026-08-26-context-management.md) | 短期记忆实现规格（已做）。表结构对照 [../architecture/database.md](../architecture/database.md)。生产库须 `alembic upgrade head` 到 `3d1c2b8a9e4f`。 |
| [2026-09-02-auto-index-on-approve.md](./2026-09-02-auto-index-on-approve.md) | 人审写盘后按文件重建 Chroma（已做） |
| [draft-generation.md](./draft-generation.md) | 入库 Job / URL 源 / 自动索引设想，不是现行架构 |
