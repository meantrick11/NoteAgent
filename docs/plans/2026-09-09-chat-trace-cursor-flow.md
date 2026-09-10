# 过程排做成 Cursor 式步骤流

> 只写规格，本文件落地前不改代码。不改 RAG、草稿审批、Documents、`assistant_final` 落库。无时长（不做 Thought 8s）。

**Goal:** 运行中也能点箭头看**完整步骤列表**；当前步闪烁；完成后该行改成 `Read go.md` 这种过去式。Thinking 行可再展开，展示该 hop 模型写出的推理/过渡文字（有则显示，没有则只有标题、无正文）。

**为什么现在像「只显示一部分」**

当前实现把过程排做成「标题只亮当前一步」：

1. **live 时箭头隐藏，且禁止点击展开**（`.msg-trace-head.live` 里 chevron `display:none`，click 直接 return）。列表其实在 DOM 里更新，但用户永远看不到。
2. **标题覆盖列表。** 用户只看见一行「正在思考 / 正在阅读」，展开后的流程被藏掉。
3. **工具 hop 的模型正文被丢掉。** `astream` 里一旦 `saw_tool`，content 不 `yield token`，也不进过程排。Cursor 的 Thinking 段落往往就是这段（或 `reasoning_content`）。我们现在 SSE 的 `thinking` 只是字符串 `"thinking"`，没有推理内容。
4. **刷新后只剩 tool stub。** `_think` / `_answer` 只活在本次前端内存；`list_messages` 的 `tool_steps` 没有思考正文。

截图里「Exploring 4 files…」下面那一长串 Read / Searched / Thinking，是**列表始终可看**，不是标题替代列表。

---

## 目标交互（浅色现有变量，不抄暗色）

```text
.msg-col
  .msg-trace
    button.msg-trace-head     当前步（live 闪烁）或结束后 Finished + ▼
    ol.msg-trace-list         live 也可展开；默认折叠
      li.step                 进行中：正在阅读笔记 go.md...（该行闪）
                              完成后：Read go.md
      li.step.think           Thinking ▼
        .step-think-body      该 hop 积累的模型文字（无则不渲染 body）
    .msg-bubble               仅最终回答
```

- **运行中也可以点总箭头**看已发生的全部步骤；当前未完成那一行闪烁。
- Thinking **单独再带一个小箭头**：点开才显示推理正文，避免把过程排撑成第二份回答。
- 主气泡仍然只有最终 assistant；工具全文、检索 chunk **不进**步骤行（步骤行最多文件名 / 查询短串）。

### 步骤文案

| 工具 | 进行中 | 完成后 |
|------|--------|--------|
| （推理 hop） | Thinking... | Thought |
| `search_relative_from_chromadb` | Searching notes... | Searched `{query}` |
| `read_file` | Reading {file}... | Read {file} |
| `list_files` | Listing notes... | Listed notes |
| `propose_note` | Proposing a note... | Proposed {file} |

总标题：live 为当前步英文（`Thinking...` / `Reading go.md...` / `Generating...`）；结束后为 `Explored 2 files, 1 search`（无工具则隐藏过程排）。live 时箭头可见，可展开。时态口径见 [2026-09-10-chat-trace-tense.md](./2026-09-10-chat-trace-tense.md)。

---

## 推理内容从哪来（必须说清）

现行 `CHAT_MODEL`（如 `deepseek-v4-flash`）**不是** Cursor Composer 那种始终吐 hidden CoT 的通道。能做的：

**采用（本计划）：** 每个 LLM hop 把**不进主气泡的文本**收成该 hop 的 `think`：

- 工具 hop：`chunk.content` 现在被丢弃，改为 `yield {event: think, data: 增量}`，前端挂到当前 Thinking 步。
- 若 chunk 带 `additional_kwargs.reasoning_content` / `reasoning`（部分 DeepSeek reasoner），同样追加进 `think`。
- 最终回答 hop 的 content 仍走 `token` 进气泡，**不要**再复制进 Thinking，避免两处同一段话。

**不采用：** 为过程排新开一张表；把 tool `output` 全文当 Thinking；假装编造推理。

无文字时：列表里仍有一条 Thinking，点开为空或隐藏 body。

**持久化（本轮最小）：** Thinking 正文**不入库**。刷新后过程排只恢复 `tool_steps`（Read / Searched）。直播当次会话里可展开看推理。若以后要刷新仍能看，再把截断 think 挂到 assistant 行 JSON（另开计划）。

---

## SSE 增量

| event | data | 前端 |
|-------|------|------|
| `thinking` | `"thinking"` | 追加一条未完成 Thinking 步（每 hop 一条，不要整回合共用一条把多次推理糊在一起） |
| `think` | 字符串增量 | 追加到**当前** Thinking 步的 `content` |
| `tool` | `{name, args}` | 当前 Thinking 标完成；追加工具步（进行中文案） |
| `tool_done` | 现有 stub 字段 | 该工具步改成 Read / Searched … |
| `generating` | `"generating"` | 若无进行中工具，标题改为正在生成回答；可新开 Thinking 仅当本 hop 还会出 `think` |
| `token` | 最终正文增量 | 气泡；不进步骤列表 |

同一 `tool` call 仍只宣布一次。`think` 与 `token` 互斥：`saw_tool` 时只 `think`，最终 hop 只 `token`。

路由已转发未知 event；确认 `think` 的 `data` 非空才 yield（空串不要推）。

---

## 前端改动（`home.html`）

1. 去掉「live 禁止展开 / 隐藏箭头」。live 时箭头可见；`.live` 只闪**标题或当前 li**，不要把整个列表藏起来。
2. `renderTraceList` 改成逐步 DOM：已完成行用 `toolFlowLabel`（Read …）；未完成行用进行中文案 + `.live`。
3. Thinking 行：内层 button 展开 `.step-think-body`（`pre-wrap`、12px、次要色）。点击内层 `stopPropagation`，避免收起整段过程排。
4. 总栏结束后：英文计数汇总 + ▼，默认折叠。live 时箭头可见，可展开。
5. 历史：`tool_steps` 仍画 Read / Searched；无 Thinking 正文则无内层展开。

---

## 后端改动（`agent.py`）

在现有 `astream` 循环里：

- hop 开始：`thinking` 或 `generating`（逻辑保持：用过工具后不再发会盖标题的假思考）。
- 每个 chunk：抽 `content` 与可选 `reasoning_content`。
- 若本 hop 已判定为 tool：content/reasoning → `think`，不 `token`。
- 若非 tool：content → `token`（与现在相同）。
- 不要把 tool hop 的 content 再拼进 `assistant_final`。

加短函数 `_reasoning_text(chunk)`，避免在循环里堆 `getattr`。

单测：脚本模型先 yield 带 `content="will search"` + `tool_calls` 的 chunk，断言存在 `think` 且 **没有** 把 `"will search"` 当作 `token`；再 `tool` / `tool_done`。无工具分片测试保持只 `token`。

---

## 文档

更新 [2026-09-09-chat-trace-summary.md](./2026-09-09-chat-trace-summary.md) 口径（live 可展开；完成后 Read；Thinking 可展开）。`architecture.md` / `frontend.md` / `chat-tools.md` 各改一句。不把 tool 全文画进过程排写进原则里。

---

## 验收

- 运行中点 ▼ 能看到**已经发生的每一步**，当前步闪烁，不是只剩标题。
- `read_file` 有结果后该行变成 `Read go.md`，不是继续「正在阅读」。
- 工具 hop 若模型写了过渡句，Thinking 展开能看到（截断到合理长度，例如前端 4k 字符，多了加省略）。
- 最终回答仍在气泡流式；草稿卡、出处、Documents 不变。
- 刷新：工具步还在；Thinking 正文可以没有。

## 不做

时长；暗色；独立轨迹表；把检索原文塞进步骤行。
