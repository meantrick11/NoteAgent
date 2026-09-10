# 出处侧栏按会话隔离 + 引用按消息重排 1..n

> 本日实现规格。不改表结构、不改工具 `source_id` 分配、不改 RAG。

**Goal:** 每个会话自己的右侧出处栏开合与未保存缓冲互不串；每条助手消息只把最终用到的引用写入 `messages.citations`，编号按该条正文首次出现压成 1..n。

## 现状

`#citePane` 是整页一块 DOM。`openConversation` 只换气泡，不切换侧栏；只有 `newChat` 会关栏。A 点开笔记再点 B，B 仍顶着 A 的栏。

引用本来就只入库**最终正文里出现过的合法** `[[cite:N]]`（不是本轮工具登记的全部 source）。落点是 PostgreSQL `messages.citations` JSON，和净化后的 `messages.content` 一起在流结束时 `append_message`。缺口是 `sanitize_answer` 保留工具原始 `source_id`：用到 3 和 5 时库里两条，气泡仍画 ③⑤。

## 做法

- 内存 `citePaneByConv[conversationId]`：切走快照，切回还原。未打开过的会话栏收起。未保存按会话暂存，切会话不弹放弃；关页或进 Documents 时若当前栏或任一快照 dirty 再确认。点保存仍 `PUT /notes/{path}`。
- `sanitize_answer`：仍丢未登记号；对保留标记按出现顺序重写成 `[[cite:1]]`…；`used[].index` 同步。流式 `token` 仍可能带着工具原始号；路由把 `assistant_final` 转成 SSE `answer`，前端用这份正文与 `sources` 对齐。渲染时再按该条消息映射一遍，兼容旧行。

## 不做

全局稳定引用号、新表、切会话时把未保存写盘。

## 验收

- A 打开笔记并改字不保存 → 切 B 无栏；切回 A 同一笔记与未保存正文还在。
- A 点关闭后再切走切回：栏收起。
- 同一会话连续两问都带引用：两条都从 ① 起；点第二条的 ① 打开第二条自己的来源。
- 本轮登记 1..3、正文只引用 2 和 3：入库正文为 `[[cite:1]]` `[[cite:2]]`，`citations` 两条且 index 为 1、2。
