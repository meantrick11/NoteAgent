# templates

FastAPI `GET /` 与 `GET /documents` 返回的 HTML。不要把笔记正文或密钥写进模板。界面布局、树交互、两条写盘路径见 [docs/architecture/frontend.md](../../../../docs/architecture/frontend.md)。

## 包含模块

| 文件 | 作用 |
|------|------|
| `home.html` | 顶栏 Chat \| Documents；Chat 会话与 SSE；Documents 一层目录树、编辑/预览、拖拽、芯片 |

页面会请求：

| 方法 | 路径 | 字段 |
|------|------|------|
| GET | `/conversations` | —（侧栏历史列表） |
| GET | `/conversations/{id}/messages` | —（某一会话的气泡） |
| PATCH | `/conversations/{id}` | `title`（重命名） |
| DELETE | `/conversations/{id}` | —（204，删会话） |
| POST | `/chat` | `question`、可选 `conversation_id` |
| POST | `/chat/review` | `thread_id`、`action`，可选 `write_action`、`file_name` |
| GET | `/documents` | —（同一页切 Documents） |
| GET | `/notes` | —（文件列表、mtime、indexed） |
| GET | `/notes/{path}` | —（正文） |
| POST | `/notes` | `file_name`（新建后入库） |
| PUT | `/notes/{path}` | `content`（保存后重建向量） |
| DELETE | `/notes/{path}` | —（删文件和向量） |
| POST | `/notes/{path}/index` | —（点「未索引」入库，不改文件） |
| POST | `/notes/folders` | `name` |
| POST | `/notes/folders/rename` | `from`、`to` |
| DELETE | `/notes/folders/{name}` | —（删文件夹内全部笔记和向量） |
| POST | `/notes/move` | `from`、`to` |

SSE：先 `event: conversation`（`{id, title}`），再 `event: token` 拼进助手气泡、`event: draft` 渲染审批卡片。后端内部的 `assistant_final` 不推给页面。

用户气泡（`.msg-row.user .msg-body`）使用 `white-space: pre-wrap`，粘贴的换行会显示成分段；助手气泡仍走 `marked`。

## 基础使用

本地改样式或按钮文案后保存 `home.html`，刷新 `http://127.0.0.1:8000`。`read_home_html()` 每次请求读盘，无需为 HTML 重启 uvicorn（除非你改了缓存逻辑）。
