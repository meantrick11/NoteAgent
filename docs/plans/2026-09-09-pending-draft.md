# 待审草稿持久化

> 本日实现规格。不改 SSE 流式、token 估算、RAG。写盘仍只发生在 `commit_review`。

**Goal:** 进程重启或切会话后，未审批草稿仍以卡片再现并要求人审；已审批/已拒绝不再出卡。

**做法:** `conversations.pending_draft` 可空 JSON（形状 = `NoteDraft.as_dict()`）。`DraftStore` 经 `ConversationStore` 覆盖写入；有 JSON = 待审，`NULL` = 无待审。前端 `GET /conversations/{id}` 回湿卡片。不把草稿写入 `messages`，不加 `written` 布尔。

## 不做

多草稿队列、前端改 bool 再写盘、任务状态机。

## 验收

- 切会话再回来：未审卡片仍在，磁盘未改。
- 重启后（库数据仍在）：未审卡片仍在；已审无卡，原气泡仍在。
- `GET /conversations/{id}/messages` 仍是气泡数组。
