# chat

HTTP 聊天、LangGraph Agent、工具、**人审之后才写盘**。不直接 `open()` 笔记文件，不直接 new Chroma 客户端。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `router.py` | `router` | `GET /`、`GET /conversations`、`GET /conversations/{id}/messages`、`PATCH /conversations/{id}`、`DELETE /conversations/{id}`、`POST /chat`、`POST /chat/review`、`POST /chat/user_exit` |
| `agent.py` | `ChatAgent` | 流式 token、吐出 draft 事件、`review()` 落盘 |
| `history.py` | `ConversationStore` | 会话/消息唯一写入口（PostgreSQL）；`create`/`rename`/`delete`；`conversation_title_from_question`、`normalize_conversation_title` |
| `drafts.py` | `DraftStore`、`NoteDraft`、`commit_review` | 按 `thread_id` 暂存提案；同意后 `create`/`write` |
| `tools.py` | `build_chat_tools` | `list_files`、`read_file`、`search_*`、`propose_note`（无写盘工具） |
| `schemas.py` | `RequestModel`、`ReviewRequest`、`ConversationOut`、`MessageOut`、`RenameConversation` | 请求/响应体 |
| [`prompts/`](prompts/README.md) | `system.txt` | 系统提示 |

## 基础使用

装配时把同一个 `DraftStore` 交给工具和 Agent：

```python
from noteagent.chat.drafts import DraftStore
from noteagent.chat.tools import build_chat_tools
from noteagent.chat.agent import ChatAgent

drafts = DraftStore()
tools = build_chat_tools(notes, retrieval, drafts)
agent = ChatAgent(model, tools, notes, drafts)

async for item in agent.stream("讲一下 for 循环", thread_id="t1"):
    # item == {"event": "token", "data": "..."} 或 {"event": "draft", "data": {...}}
    ...
agent.review("t1", "approve")
```

HTTP：

- `GET /conversations`：侧栏历史列表（按 `updated_at` 倒序）
- `GET /conversations/{id}/messages`：某一会话的全部气泡（按时间正序）
- `PATCH /conversations/{id}` JSON：`{"title": "新名字"}`；重命名（`strip`+折叠空白，空 400、超 80 字符 400），**不改 `updated_at`**
- `DELETE /conversations/{id}`：204，删会话及其消息（`ON DELETE CASCADE`）
- `POST /chat` JSON：`{"question": "...", "conversation_id": "<uuid>"?}`；`conversation_id` 可选，缺省则新建会话。SSE 先推 `event: conversation`（`{"id", "title"}`），再 `event: token` / `event: draft`
- `POST /chat/review` JSON：`{"thread_id": "1", "action": "approve"|"reject"|"override", "write_action"?, "file_name"?}`
- `POST /chat/user_exit`：往 `context.md` 追加一行会话结束记录

用户可见历史存 PostgreSQL；`ChatAgent` 仍用 `InMemorySaver`，进程重启后**不会**自动带上旧轮次的模型上下文。

```bash
uv run pytest tests/unit/test_chat_history.py tests/integration/test_app.py -q
```
