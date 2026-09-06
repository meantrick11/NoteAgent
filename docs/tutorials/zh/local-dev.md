# 本机开发

在仓库根目录用 Python 跑应用，不经过 Docker。需要自己装 Python、uv、PostgreSQL，并允许首次下载嵌入模型。

零基础只想看界面：走 [getting-started.md](getting-started.md)。

## 依赖

- Python **3.13**（见根目录 `pyproject.toml` 的 `requires-python`）
- [uv](https://docs.astral.sh/uv/)
- 本机 PostgreSQL（对话历史；测试用内存 SQLite，不需要）

## 数据库

1. 启动 PostgreSQL。
2. 建库：`CREATE DATABASE noteagent;`
3. 复制环境文件并填写连接串（前缀必须是 `postgresql+psycopg://`，不是 `postgresql://`）：

```powershell
Copy-Item .env.example .env
```

```text
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent
```

4. 安装依赖并迁移到现行 head（含摘要 / watermark / stub 列）：

```powershell
uv sync
uv run alembic upgrade head
```

代码已升级而库未升时，发聊天会 500（缺 `running_summary` 等列）。看表用 psql 或图形客户端连同一库；Windows 终端若是 GBK，先 `SET client_encoding TO 'UTF8';` 或 `chcp 65001`。

## 嵌入模型

`.env.example` 默认：

- `EMBEDDING_CACHE_DIR=var/models`（相对仓库根）
- `EMBEDDING_LOCAL_FILES_ONLY=false`（第一次允许从网络下载 MiniLM）

下载完成后可改成 `true`，避免以后误连 Hugging Face。不要指向别的机器上的绝对路径。

## 启动

```powershell
uv run python main.py
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

也要填 `DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`、`CHAT_MODEL`，否则对话会失败。

## 测试与索引

```powershell
uv run pytest -q
```

人审写盘后会按该文件重建向量。collection 损坏时仍可手动重建一篇：

```powershell
uv run python scripts/index_notes.py Agent.md
```

密钥冒烟：`uv run python scripts/sdk_smoke.py`。说明见 [`scripts/README.md`](../../../scripts/README.md)。

## 环境变量

| 变量 | 作用 |
|------|------|
| `DEEPSEEK_API_KEY` | 聊天模型密钥 |
| `DEEPSEEK_API_BASE` | 可选，自定义 API 地址 |
| `CHAT_MODEL` | 默认 `deepseek-v4-flash` |
| `NOTES_DIR` | 笔记目录，默认 `notes` |
| `CHROMA_DIR` | 向量库目录，默认 `chromadb_persist` |
| `CHROMA_COLLECTION` | collection 名 |
| `DATABASE_URL` | PostgreSQL，前缀须为 `postgresql+psycopg://` |
| `CHAT_CONTEXT_WINDOW` 等 | 上下文窗口、压缩、stub、`CHAT_MAX_TOOL_HOPS`；见 `.env.example` |
| `EMBEDDING_MODEL` | SentenceTransformer 模型名 |
| `EMBEDDING_CACHE_DIR` | 本地模型缓存 |
| `EMBEDDING_LOCAL_FILES_ONLY` | `true` 时不联网下载 |
| `HOST` / `PORT` | 服务监听 |
| `LOG_DIR` / `LOG_LEVEL` | 日志 |

## 仓库目录

| 目录/文件 | 作用 |
|-----------|------|
| [`src/noteagent/`](../../../src/noteagent/README.md) | 全部应用代码 |
| [`main.py`](../../../main.py) | 读配置、打日志、启动 uvicorn |
| [`notes/`](../../../notes/README.md) | 正式 Markdown 数据 |
| [`scripts/`](../../../scripts/README.md) | 索引、API 冒烟 |
| [`tests/`](../../../tests/README.md) | 单测 / 集成测（无真实 LLM） |
| [`evals/`](../../../evals/README.md) | 提示词/Agent/RAG 黄金集；人工打分，不进默认 CI |
| [`docs/`](../../README.md) | 架构、教程、参考 |
| [`var/`](../../../var/README.md) | 日志等运行时数据（不入库） |

系统设计：[架构说明书](../../architecture/architecture.md)。

## Docker 卷（改镜像时）

`docker compose` 覆盖 `HOST`、`DATABASE_URL`、`EMBEDDING_CACHE_DIR=var/models`、`EMBEDDING_LOCAL_FILES_ONLY=true`。不要指望把 Windows 本机的 embedding 路径挂进容器。

| Volume | 作用 |
|--------|------|
| `./notes` bind | 正式 Markdown，可在宿主机直接打开 |
| `chroma_data` | Chroma 派生索引 |
| `pgdata` | 会话库 |
| `app_logs` | `var/logs`；不要挂载整个 `var/`，否则会盖住镜像里的 MiniLM 缓存 |

compose 里 Postgres 用户/库名为 `noteagent`（仅本地默认）。聊天模型仍走外网，容器不内置 LLM。
