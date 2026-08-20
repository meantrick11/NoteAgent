# plans

给实现 Agent 按任务执行的规格。不是运行时架构契约；架构仍以 `docs/architecture/knowledge-workflow-v1.md` 为准。冲突时以架构文档的产品边界为准，以本目录的任务步骤为准去改代码。

## 包含模块

| 文件 | 说明 |
|------|------|
| [2026-08-20-chat-history-persistence.md](./2026-08-20-chat-history-persistence.md) | 会话列表 + PostgreSQL 消息落库（展示层） |
| [2026-08-20-conversation-rename-delete.md](./2026-08-20-conversation-rename-delete.md) | 侧栏重命名、删除（含确认弹层） |
