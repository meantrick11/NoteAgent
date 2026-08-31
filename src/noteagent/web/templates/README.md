# templates

FastAPI `GET /` 返回的 HTML。不要把笔记正文或密钥写进模板。

## 包含模块

| 文件 | 作用 |
|------|------|
| `home.html` | 单页：会话侧栏（历史/重命名/删除）、对话框、SSE 渲染 Markdown、草稿审批卡片 |

页面会请求：

| 方法 | 路径 | 字段 |
|------|------|------|
| GET | `/conversations` | —（侧栏历史列表） |
| GET | `/conversations/{id}/messages` | —（某一会话的气泡） |
| PATCH | `/conversations/{id}` | `title`（重命名） |
| DELETE | `/conversations/{id}` | —（204，删会话） |
| POST | `/chat` | `question`、可选 `conversation_id` |
| POST | `/chat/review` | `thread_id`、`action`，可选 `write_action`、`file_name` |
| POST | `/chat/user_exit` | `question`、`thread_id`（空实现，不写 `context.md`） |

SSE：先 `event: conversation`（`{id, title}`），再 `event: token` 拼进助手气泡、`event: draft` 渲染审批卡片。后端内部的 `assistant_final` 不推给页面。

## 基础使用

本地改样式或按钮文案后保存 `home.html`，刷新 `http://127.0.0.1:8000`。`read_home_html()` 每次请求读盘，无需为 HTML 重启 uvicorn（除非你改了缓存逻辑）。
