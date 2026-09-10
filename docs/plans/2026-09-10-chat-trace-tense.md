# 过程排时态：进行中 ing，结束后过去式

> 只改 [`home.html`](../../src/noteagent/web/templates/home.html) 过程排文案与显隐。不改 Agent、SSE 事件集合、RAG、草稿、Documents。Thinking 正文仍不入库。无时长（不做 Thought 8s）。

**Goal:** 用户发一句后，过程排不再从开场到结束一直停在 `Thinking`。进行中用 `Thinking...` / `Reading…` / `Generating...`；步完成后改成 `Thought` / `Read` / `Explored`。无工具的回合结束后把过程排藏掉，和刷新历史一致。

---

## 解决什么问题

当时现象：给助手发消息，标题**一直**是 `Thinking`，流结束了还是。

根因不在模型「没思考完」，而在前端把几种不同阶段都画成 Thinking：

1. **无工具回合把空汇总写成 Thinking。** `englishSummary` 在没有任何 `read_file` / `search_*` 等工具步时，固定返回 `"Thinking"`（live 为 `"Thinking..."`）。闲聊、直接回答本来就不调工具。刷新后 `tool_steps=[]` 会隐藏过程排，所以只有「当场打完」那条看起来坏了。
2. **开始出正文后标题仍可能掉回 Thinking...** 第一个 `token` 把 `_think` 标完成，此时没有「进行中」的步，`liveTraceLabel` 回落到上面的汇总。一边打字一边还在闪 Thinking...。
3. **`generating` 被当成又一次 Thinking。** 后端用过工具后 hop 开头发 `generating`（避免再盖一层假思考）。前端却和 `thinking` 走同一分支，再 push `_think`。`toolLiveLabel` 对 `_think` 一律 `"Thinking..."`。即使用过工具，写最终回答时标题也会从 `Read xx.md` 退回 Thinking...。
4. **时态不一致。** 进行式（ing）只该出现在未完成的步。完成后的思考行仍写 `Thinking`（应为 `Thought`）；总标题结束后仍写 `Exploring …`（应为 `Explored …`）。工具单行里 `Read` / `Searched` / `Listed` / `Proposed` 已经是过去式，同一规则要补到 Thinking 行和总标题。

不在本轮：把检索原文塞进步骤；持久化 Thought 正文；暗色；Thought 时长。

---

## 具体怎么解决

全部在 `home.html` 的 `steps[]` + `paintTrace` / `finishTrace`。后端继续：`thinking` →（可选 `think` / `tool` / `tool_done`）→ 用过工具后 `generating` → `token`。

### 阶段拆开

| SSE | 前端步 `name` | live 标题 | 列表 |
|-----|---------------|-----------|------|
| `thinking` | `_think` | Thinking... | 进行中可闪；完成后有正文才留一行 **Thought** |
| `generating` | `_gen`（不要再用 `_think`） | Generating... | 不进列表 |
| 第一个 `token` 且还没有进行中的 `_gen` | 补 `_gen` | Generating... | 同上。覆盖「直答、没有 generating 事件」 |
| `tool` / `tool_done` | 工具名 | Reading… / Read … | 与现在相同，过去式已对 |

`token` 时只结束 `_think`，**不要**把 `_gen` 标完成，这样写回答期间总标题保持 Generating...。

`liveTraceLabel`：有未完成步 → 该步进行中文案；否则有真实工具 → live 汇总 `Exploring …`；否则 `Generating...`。禁止把「已经在写正文」写成 Thinking...。

### 时态表

| 阶段 | 进行中（`!status`） | 已完成 |
|------|---------------------|--------|
| 推理 hop | Thinking... | Thought |
| 写最终回答 | Generating... | 不进列表 |
| read_file | Reading {file}... | Read {file} |
| search | Searching notes... | Searched {query} |
| list_files | Listing notes... | Listed notes |
| propose_note | Proposing a note... | Proposed {file} |
| **总标题** | 当前步 ing | 有真实工具：`Explored 2 files, 1 search`；无工具：**隐藏过程排** |

`englishSummary(live)`：`live === true` 且有 read/search 用 `Exploring`；结束后用 `Explored`。仅 list/propose 时 live 用 `Listing notes...` / `Proposing a note...`，结束后 `Listed notes` / `N proposal(s)`。无工具且非 live 的 `"Thinking"` 不再作为结束标题（`finishTrace` 直接 hidden）。

`finishTrace`：先把未完成步标 `ok`。若没有任何 `name` 不以 `_` 开头的步，隐藏 `.msg-trace`（与 `appendMessage` 历史空 `tool_steps` 一致）。有工具则画 Explored 汇总并默认折叠。

### 不改

- `agent.py` / 路由 SSE 形状
- 草稿卡、出处、Documents
- Thinking 入库

---

## 文档

[`frontend.md`](../architecture/frontend.md)、[`architecture.md`](../architecture/architecture.md) 过程排一句：无工具结束后不留排；进行中 ing、完成后 Thought / Explored；`generating` 为 Generating...。[`chat-tools.md`](../architecture/chat-tools.md) 同步一句。本文件取代「结束后 Exploring / 完成思考行仍叫 Thinking」的口径；步骤流交互仍见 [2026-09-09-chat-trace-cursor-flow.md](./2026-09-09-chat-trace-cursor-flow.md)。

---

## 验收

- 闲聊 / 不调工具：先 `Thinking...`，正文起后 `Generating...`，结束后过程排消失。
- 有 search/read：进行中 Reading/Searching…；列表完成后 Read / Searched；有思考正文的行是 Thought；写回答时总标题 Generating...；整回合结束总标题 Explored …。
- 点 ▼ 仍能看到已发生的工具步。草稿、出处、Documents 不变。
