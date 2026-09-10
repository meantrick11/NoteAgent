# 流式输出与一行工具过程

> 真流式 token 的原始规格。过程排、`thinking` 不盖工具步骤、结束动作汇总见 [2026-09-09-chat-trace-summary.md](./2026-09-09-chat-trace-summary.md)。不改 RAG、草稿持久化、Documents。主气泡仍是最终 assistant 正文。

**Goal:** 最终回答按 SSE token 边收边画；助手气泡顶部一行可闪烁摘要，点击展开本回合工具步骤。刷新后用已有 `role=tool` stub 重建，不新增表、不把工具全文当气泡。

**产品口径变更：** 原先「前端完全不画工具过程」。改为「工具过程不进主气泡，收成一行可展开摘要」。

---

## 1. 为什么现在看起来不像流式

[`ChatAgent.stream`](../../src/noteagent/chat/agent.py) 对 `bound.astream` 的每个 chunk 只写入 `hop_tokens`，等这一跳拼成完整 `AIMessage` 后，若没有 `tool_calls` 才一次性 `yield token`。

这是为了 **工具 hop 必须拿到完整参数再 `ainvoke`**。最终正文 hop 不需要等全文才能给前端。改法：两件事拆开——拼完整消息给工具；正文 chunk 立刻 SSE。

[`home.html`](../../src/noteagent/web/templates/home.html) `ask()` 已经按每次 `token` 事件追加 `rawText`。路由 [`POST /chat`](../../src/noteagent/chat/router.py) 已转发 `token`，并把 `assistant_final` 留给落库（不推浏览器）。

---

## 2. SSE 契约

| event | 何时 | data | 推浏览器 |
|-------|------|------|----------|
| `conversation` | 写完 user 行之后 | `{id, title}` | 是 |
| `thinking` | 每一跳 `astream` 开始 | `"thinking"` | 是 |
| `tool` | 即将 `ainvoke` | `{name, args}` | 是 |
| `tool_done` | `append_tool_stub` 之后 | `{name, status, preview, arguments}` 均为 stub 截断值 | 是 |
| `token` | 最终正文 hop 的 content 增量 | 字符串 | 是 |
| `sources` | 最终 hop `sanitize_answer` 之后 | citation 列表 | 是 |
| `draft` | 循环结束若有 pending | `NoteDraft.as_dict()` | 是 |
| `assistant_final` | 最终全文 | 字符串 | **否**，只落库 |

工具 hop：若 chunk / 拼好的消息带 `tool_calls` 或 `tool_call_chunks`，该跳 **不** `yield token`。

---

## 3. 代码落点

| 文件 | 改动 |
|------|------|
| `src/noteagent/chat/agent.py` | thinking / 增量 token / tool / tool_done |
| `src/noteagent/chat/history.py` | `MessageRecord.tool_steps`；`list_messages` 挂同 turn stub |
| `src/noteagent/chat/schemas.py` | `ToolStepOut`；`MessageOut.tool_steps` |
| `src/noteagent/chat/router.py` | 序列化 `tool_steps` |
| `src/noteagent/web/templates/home.html` | 摘要行 UI + SSE 处理 |
| `docs/architecture/{frontend,architecture,chat-tools}.md` | 口径 |
| 单测 / `tests/integration/test_app.py` | 多 token、tool_steps、仍无 `role=tool` 行 |

---

## 4. 历史重建

`list_messages` 查出该会话全部 message（含 tool），返回给 HTTP 的仍只有 user/assistant。每条 assistant 的 `tool_steps` = 同一 `turn_id` 的 tool 行，字段：`name` ← `tool_name`，`status`，`preview` ← `output_preview`，`arguments` ← `tool_arguments`。

user 行 `tool_steps=[]`。无工具的 assistant 为 `[]`，前端不画 `.msg-trace`。

审批「已写入」目前只在前端插气泡、不入库，不污染历史。

---

## 5. 前端结构与文案

```text
.msg-bubble
  .msg-trace            无步骤则 hidden
    .msg-trace-head     一行 + chevron；.live 时 opacity 闪烁
    .msg-trace-list     默认折叠
  .msg-body
```

点击表头展开/收起。浅色现有变量，不抄 Cursor 深色。

| 工具 | 进行中 | 完成后 |
|------|--------|--------|
| （无） | 正在思考... | 不显示摘要行 |
| `list_files` | 正在列出笔记... | 已列出笔记 |
| `read_file` | 正在读取笔记... | 已读取 `{file_name}` |
| `search_relative_from_chromadb` | 正在检索类似笔记片段... | 已检索笔记片段 |
| `propose_note` | 正在提交草稿... | 已提交草稿 |
| 其它 | 正在调用工具 {name}... | 已调用 {name} |
| status=error | — | {name} 失败 |

多步汇总：「调用了 N 个工具」。单步用完成后的那句。

`ask()`：先画空助手气泡并思考闪烁 → 处理事件 → 结束去 `.live`、折叠。`openConversation` 用 `tool_steps` 同样渲染（默认折叠）。`sources` 后带 citations 重绘 `rawText`。

---

## 6. 验收

- 无工具：气泡随 token 变长。
- 有工具：过程只在摘要/列表；最终句流式；落库是 `assistant_final` 全文。
- 刷新后可展开；GET messages 无 `role=tool` 元素。
- 草稿卡片、出处、Documents、会话 CRUD 行为不变。

## 不做

WebSocket；工具全文进气泡；独立轨迹表；暗色整站。
