# NoteAgent

个人学习笔记助手。对话里把值得保留的内容整理成 Markdown 草稿，**经前端审批后**才写入 `notes/`，并按该文件重建 Chroma。检索仍是粗 RAG（字符切块 + MiniLM）。

正式说明：[项目架构书](docs/architecture/architecture.md)。工具参数、上下文公式、表结构见同目录附件。阅读顺序见 [docs/README.md](docs/README.md)。提示词人工评测见 [evals/](evals/README.md)。

## 仓库里有什么

| 目录/文件 | 作用 |
|-----------|------|
| [`src/noteagent/`](src/noteagent/README.md) | 全部应用代码 |
| [`main.py`](main.py) | 读配置、打日志、启动 uvicorn |
| [`notes/`](notes/README.md) | 正式 Markdown 数据 |
| [`scripts/`](scripts/README.md) | 索引、API 冒烟 |
| [`tests/`](tests/README.md) | 单测 / 集成测（无真实 LLM） |
| [`evals/`](evals/README.md) | 提示词/Agent/RAG 黄金集；人工打分，不进默认 CI |
| [`docs/`](docs/README.md) | 架构与参考 |
| [`var/`](var/README.md) | 日志等运行时数据（不入库） |

## 启动

```bash
uv sync
cp .env.example .env
# 填 DEEPSEEK_API_KEY；确认 EMBEDDING_* 指向本机模型缓存
uv run python main.py
```

浏览器打开 `http://127.0.0.1:8000`。

聊天：`POST /chat`（SSE）。侧栏可切换、重命名、删除历史（`PATCH`/`DELETE /conversations/{id}`）。有笔记提案时前端出卡片，`POST /chat/review` 同意后才写盘。模型上下文是库里 watermark 之后的 Persistent（含 tool stub）+ `running_summary` + 当前 Turn 内存 Runtime；气泡接口不返回 tool 行。

### PostgreSQL（对话历史）

1. 本机启动 PostgreSQL 服务
2. 建库：`CREATE DATABASE noteagent;`
3. `.env` 设置 `DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent`
4. 迁移建表（现行 head `3d1c2b8a9e4f`，含摘要 / watermark / stub 列）：`uv run alembic upgrade head`
5. 再 `uv run python main.py`

代码已升级而库未升时，发聊天会 500（缺 `running_summary` 等列）。查看表用 psql / 图形客户端连同一库；Windows 终端若是 GBK，先 `SET client_encoding TO 'UTF8';` 或 `chcp 65001`。

## 环境变量

| 变量 | 作用 |
|------|------|
| `DEEPSEEK_API_KEY` | 聊天模型密钥 |
| `DEEPSEEK_API_BASE` | 可选，自定义 API 地址 |
| `CHAT_MODEL` | 默认 `deepseek-v4-flash` |
| `NOTES_DIR` | 笔记目录，默认 `notes` |
| `CHROMA_DIR` | 向量库目录，默认 `chromadb_persist` |
| `CHROMA_COLLECTION` | collection 名 |
| `DATABASE_URL` | PostgreSQL 连接串，前缀须为 `postgresql+psycopg://` |
| `CHAT_CONTEXT_WINDOW` 等 | 上下文窗口、压缩比例、stub 截断、`CHAT_MAX_TOOL_HOPS`；见 `.env.example` |
| `EMBEDDING_MODEL` | SentenceTransformer 模型名 |
| `EMBEDDING_CACHE_DIR` | 本地模型缓存 |
| `EMBEDDING_LOCAL_FILES_ONLY` | `true` 时不联网下载 |
| `HOST` / `PORT` | 服务监听 |
| `LOG_DIR` / `LOG_LEVEL` | 日志 |

审批写入后会自动按该文件重建向量。collection 损坏时仍可手动重建：

```bash
uv run python scripts/index_notes.py Agent.md
```

测试：`uv run pytest -q`
