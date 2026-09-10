# 过程排：实时当前步骤，结束为 Finished

> 已被 [2026-09-09-chat-trace-cursor-flow.md](./2026-09-09-chat-trace-cursor-flow.md) 取代（英文汇总、live 可展开、Thinking 正文）。

> 本日实现规格。无时长。不改 RAG、草稿、Documents、落库规则。

**Goal:** 进行中那一排只显示并闪烁**当前步骤**；整回合结束后变为 `Finished` + 向下箭头，点击展开/收回流程。

**Architecture:** 后端仍发 `thinking` / `generating` / `tool` / `tool_done`。前端 `steps[]` 记录流程；live 标题只取未完成的最后一步。

## 进行中（闪烁）

| 当前步骤 | 文案 |
|----------|------|
| `thinking` | 正在思考... |
| `search_relative_from_chromadb` | 正在调用检索工具... |
| `read_file` | 正在阅读笔记 {file}... |
| `list_files` | 正在列出笔记... |
| `propose_note` | 正在提交草稿... |
| 正在吐最终 token / `generating` 且无进行中工具 | 正在生成回答... |

箭头在 live 时隐藏，不可展开。

## 结束后

同一排：`Finished` + `▼`。默认折叠。点击展开为时间顺序短句（思考 / 调用检索工具 / 阅读笔记 go.md / 生成回答），再点收回（箭头旋成朝上）。无时长。无工具的历史刷新没有思考步入库，过程排隐藏；本回合直播结束仍可展开（前端记了思考/生成回答）。

## SSE

- `thinking`：未用工具的 hop 开头；前端记下思考步。
- `generating`：用过工具后的 hop 开头；标题改为正在生成回答（若紧接着又 `tool` 则改回该工具）。
- `tool` / `tool_done`：当前步骤换成对应工具文案。

## 不做

时长；动作计数汇总当标题；WebSocket；把思考步写入 PostgreSQL。
