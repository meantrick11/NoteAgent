# plans

给实现 Agent 按任务执行的规格。现行系统以 [../architecture/architecture.md](../architecture/architecture.md) 为准。上下文公式以 [../architecture/context-management.md](../architecture/context-management.md) 为准。

## 文件

| 文件 | 说明 |
|------|------|
| [2026-08-20-chat-history-persistence.md](./2026-08-20-chat-history-persistence.md) | 会话列表 + PostgreSQL 消息落库（已做） |
| [2026-08-20-conversation-rename-delete.md](./2026-08-20-conversation-rename-delete.md) | 侧栏重命名、删除（已做） |
| [2026-08-26-context-management.md](./2026-08-26-context-management.md) | 短期记忆实现规格（已做）。表结构对照 [../architecture/database.md](../architecture/database.md)。生产库须 `alembic upgrade head` 到 `3d1c2b8a9e4f`。 |
| [2026-09-02-auto-index-on-approve.md](./2026-09-02-auto-index-on-approve.md) | 人审写盘后按文件重建 Chroma（已做） |
| [2026-09-05-documents-panel.md](./2026-09-05-documents-panel.md) | Chat \| Documents；一层目录分类；保存后按路径重索引 |
| [2026-09-06-readme-tutorials.md](./2026-09-06-readme-tutorials.md) | 根 README 首页 + `docs/tutorials/`（按层级 × 语言）（已做） |
| [2026-09-06-readme-homepage.md](./2026-09-06-readme-homepage.md) | 根 README 按 Adventure 结构写清功能与起步（已做） |
| [2026-09-06-prompt-eval.md](./2026-09-06-prompt-eval.md) | 离线提示词评测：黄金集、L1 打分、一键脚本、`n05.md` 结果（已做） |
| [2026-09-07-chat-citations.md](./2026-09-07-chat-citations.md) | 聊天出处：`[[cite:N]]` → ①；`messages.citations` JSON；右侧笔记预览 |
| [2026-09-07-chat-cite-edit.md](./2026-09-07-chat-cite-edit.md) | Chat 气泡同栏对齐；出处侧栏可保存（`PUT /notes`），无预览无删除 |
| [2026-09-09-pending-draft.md](./2026-09-09-pending-draft.md) | 待审草稿进 `conversations.pending_draft`；打开会话回湿卡片 |
| [2026-09-09-chat-stream-trace.md](./2026-09-09-chat-stream-trace.md) | 真流式 token；助手气泡一行可展开工具过程 |
| [2026-09-09-chat-trace-summary.md](./2026-09-09-chat-trace-summary.md) | 过程排实时当前步骤；结束 `Finished` + ▼ 展开流程 |
| [2026-09-09-chat-trace-cursor-flow.md](./2026-09-09-chat-trace-cursor-flow.md) | Cursor 式步骤流；英文汇总标题；live 可展开；Thinking 看推理 |
| [2026-09-09-cite-pane-isolation.md](./2026-09-09-cite-pane-isolation.md) | 出处侧栏按会话快照；每条助手消息引用重排 1..n |
| [2026-09-10-chat-trace-tense.md](./2026-09-10-chat-trace-tense.md) | 过程排时态：ing / Thought·Explored；generating 不再画成 Thinking；无工具结束藏排 |
| [draft-generation.md](./draft-generation.md) | 入库 Job / URL 源 / 自动索引设想，不是现行架构 |
