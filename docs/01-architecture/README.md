# 当前架构与设计

本目录只描述已经实现的代码，主线是 [architecture.md](architecture.md)。

- [数据库：Conversation/Message、摘要和草稿](database.md)
- [聊天上下文与压缩](../03-modules/chat/context-management.md)
- [聊天工具/API 契约](../02-api/chat-tools.md)
- [当前前端](../03-modules/frontend/frontend.md)
- [当前检索与索引身份](../03-modules/retrieval/retrieval.md)
- [日志与追踪](../04-ops/observability.md)

目标架构由 [NoteAgent-docs ARC-001](../../../NoteAgent-docs/docs/03-architecture/ARC-001-目标架构与迁移边界.md) 管理。当前未使用 LangGraph checkpoint 保存消息；整体回退尚未实现。
