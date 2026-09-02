# chat

HTTP 聊天、`bind_tools` Agent、工具、**人审之后才写盘**。不直接 `open()` 笔记文件，不直接 new Chroma 客户端。无 `create_agent` / `InMemorySaver`。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `router.py` | `router` | `GET /`、会话 CRUD、`POST /chat`、`POST /chat/review` |
| `agent.py` | `ChatAgent` | `bind_tools` 循环；SSE token / 内部 `assistant_final` / draft；每步写 tool stub；hop 上限来自 budget |
| `history.py` | `ConversationStore` | 会话/消息唯一写入口；`start_turn`、`append_tool_stub`、`apply_compact`、`list_persistent_after_watermark` |
| `context_budget.py` | `ContextBudget`、`budget_from_settings` | 窗口 W、压缩比例、stub 截断、`max_tool_hops` |
| `context_tokens.py` | `estimate_tokens`、`prefix_until_tokens` | 字符/4 估算，无 tiktoken |
| `context_compact.py` | `group_turns`、`select_turns_to_drop` 等 | 完整 Turn 边界压缩 |
| `context_pack.py` | `build_pack` | Persistent + summary + 当前 Runtime；用户句若有编号/`##` 标题则注入「材料标题树」 |
| `drafts.py` | `DraftStore`、`NoteDraft`、`ProposeNoteInput`、`commit_review` | 按会话暂存提案；同意后写盘并同步 Chroma |
| `tools.py` | `build_chat_tools` | `list_files`、`read_file`、`search_*`、`propose_note`（无写盘；四动作）。契约：[docs/architecture/chat-tools.md](../../../docs/architecture/chat-tools.md) |
| `schemas.py` | 请求/响应体 | 含 `ConversationOut`、`MessageOut` |
| [`prompts/`](prompts/README.md) | `system.txt` | 现行五要素提示（含 replace/delete 写模式）；归档 [`prompts/iterations/`](prompts/iterations/README.md) v1–v7 |

## 基础使用

装配时把同一个 `DraftStore` 交给工具和 Agent：

```python
from noteagent.chat.drafts import DraftStore
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.chat.context_budget import budget_from_settings
from noteagent.chat.tools import build_chat_tools
from noteagent.chat.agent import ChatAgent

drafts = DraftStore()
tools = build_chat_tools(notes, retrieval, drafts)
agent = ChatAgent(model, tools, notes, drafts, history=history, budget=budget_from_settings(settings), retrieval=retrieval)

async for item in agent.stream("讲一下 for 循环", thread_id="t1", turn_id=start_turn()):
    # token / draft；assistant_final 只给路由写库，不推前端
    ...
agent.review("t1", "approve")
```

HTTP：

- `GET /conversations`：侧栏历史（按 `updated_at` 倒序）
- `GET /conversations/{id}/messages`：气泡，仅 `user`/`assistant`（**无 tool stub**）
- `PATCH` / `DELETE /conversations/{id}`：重命名不改 `updated_at`；删除 CASCADE
- `POST /chat` JSON：`{"question": "...", "conversation_id": "<uuid>"?}`。先落库 user（带 `turn_id`），SSE：`conversation` → `token` / `draft`；结束后只把最终 assistant 入库
- `POST /chat/review`：审批草稿；写盘成功后同步该文件向量

跨回合记忆 = watermark 后 Persistent（user + 最终 assistant + tool stub）+ `running_summary`。当前 Turn 工具全文只活在本次 `stream()` 的 Runtime。压缩阈值全部来自 Settings，不在 compact/agent 里写死窗口数字。

## 工具循环与 stub

不是 LangChain AgentExecutor。`bind_tools` 只把工具 schema 交给模型；`ChatAgent.stream` 自写循环：`astream(pack.messages)` → 有 `tool_calls` 则 `tool.ainvoke`（本地函数）→ `json.dumps` 得到 `out`。

- **Runtime：** `ToolMessage(content=out)` 进局部 list，下一 hop 由 `build_pack` 接到消息末尾（本 Turn stub 不重复装入）。
- **库：** 立刻 `append_tool_stub`。预览用 `prefix_until_tokens(out, CONTEXT_STUB_PREVIEW_TOKENS)`，token 估算是 `estimate_tokens` = 约 4 字符/1，**不是** API `usage`。参数按字符截 `CONTEXT_ARGS_PREVIEW_CHARS`。
- 无 `tool_calls` 时结束本 Turn；路由用 `assistant_final` 只入库最终正文。

契约全文：[docs/architecture/context-management.md](../../../docs/architecture/context-management.md) §7.1。

记笔记质量与意图门的人工集：[evals/](../../../evals/README.md)（不要放进 `tests/`）。

```bash
uv run pytest tests/unit/test_chat_agent_context.py tests/unit/test_context_store.py tests/unit/test_context_pack.py tests/integration/test_app.py -q
```
