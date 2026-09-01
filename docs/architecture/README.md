# architecture

本目录文档分工如下。实现前先看 [`docs/README.md`](../README.md) 的阅读顺序。

## 文件

| 文件 | 大概内容 | 对实现的约束 |
|------|----------|----------------|
| [architecture.md](./architecture.md) | **项目架构书**：4.1 前端、4.2 后端、4.3 数据库、4.4 笔记 | 按用户路径；细节跟小节链接 |
| [chat-tools.md](./chat-tools.md) | Agent 四工具：工作流、参数、意图门、人审落盘 | **现行契约**；以 `tools.py` / `drafts.py` 为准 |
| [database.md](./database.md) | PostgreSQL 表、Store、现行/目标列与实例 | 聊天落库；向量/笔记文件不在本库 |
| [DESIGN.md](./DESIGN.md) | Phase 1 屏幕/音频笔记的**历史**设计 | 不实现 |
| [draft-generation.md](./draft-generation.md) | 笔记草稿生成与入库（目标 + 代码证据） | 产品边界；文首证据优先 |
| [context-management.md](./context-management.md) | 短期记忆全文 | ChatAgent 上下文契约（代码已落地） |
| 评测数据 | 不在本目录 | 仓库根 [`evals/`](../../evals/README.md) |
| `noteagent-architecture.canvas.tsx` | 结构画布（目标流程） | 可视化，非 API 契约 |
| `noteagent-system-workflow.canvas.tsx` | 系统流程画布 | 同上 |
