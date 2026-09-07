# NoteAgent

个人学习笔记助手。本机 Web · Docker 或 uv · 人审后写 Markdown。

在浏览器里对话，把值得保留的内容整理成 Markdown 草稿，**你点同意之后**才写入本地 `notes/`，并按该文件重建检索索引。单用户、单进程；聊天模型走外网（默认 DeepSeek）；笔记是普通 `.md`，可以自己打开、搬家。

当前版本：`0.1.0`（见 `pyproject.toml`）。

## 目录

- [演示](#演示)
- [亮点](#亮点)
- [功能说明](#功能说明)
- [快速开始](#快速开始)
- [开发](#开发)
- [使用说明](#使用说明)
- [数据放哪](#数据放哪)
- [文档](#文档)
- [项目结构](#项目结构)

## 演示

录屏稍后放这里。

## 亮点

| 点 | 含义 |
|----|------|
| 人审写盘 | 模型不能直接改文件。`propose_note` 只把草稿放进内存；同意后才 `create` / `append` / `replace` / `delete`。细节：[聊天工具](docs/architecture/chat-tools.md) |
| Chat \| Documents | 同一张页面两套主界面：聊天管会话，Documents 管磁盘上的笔记。布局：[前端](docs/architecture/frontend.md) |
| 一层目录 | 允许 `notes/Folder/Note.md`，禁止两层和 `..`。根下 `notes/*.md` 为未进文件夹的篇 |
| 派生检索 | Chroma 由 Markdown 重建。索引失败不回滚已写入的笔记。[检索](docs/architecture/retrieval.md) |

三条运行时原则：LLM 只出提案；磁盘只走人类操作（聊天审批、Documents、或 Chat 出处侧栏保存）；聊天气泡不画工具过程。

## 功能说明

### 聊天

左侧是会话列表（PostgreSQL）。点会话加载气泡；底栏输入，Enter 发送、Shift+Enter 换行。流式回复走 `POST /chat`（SSE）。同一时刻只能发一句。

气泡只有 `user` 和最终 `assistant`（与输入框同宽对齐）。`list_files` / 检索 / 提案等工具调用给模型和日志，不进侧栏。点回复里的 ① 可在右侧改该笔记并保存（`PUT /notes`，与 Documents 相同重索引）；无预览、无删除。

跨回合给模型的上下文 = 摘要水位线之后的 Persistent（含 tool stub）+ `running_summary` + 当前这一轮内存里的 Runtime。公式与截断：[上下文管理](docs/architecture/context-management.md)。会话表：[数据库](docs/architecture/database.md)。

### 人审卡片

模型认为该记笔记时，会调用 `propose_note`，前端弹出卡片：同意或拒绝。`create`、`append` 可以改目标文件名。只有 `POST /chat/review` 成功后才写 `notes/`。拒绝则丢弃该草稿，不改磁盘、不改向量。

### Documents

顶栏切到 Documents：左树、右编辑器 + Markdown 预览。保存、新建、移动、删除都是人写盘，不经过 Agent。保存后按该相对路径删旧向量再整篇索引。树上看「已索引 / 未索引」芯片（未索引可点入库）。只拖笔记、不拖文件夹；一层目录。拖拽、芯片、弹窗细节见 [前端](docs/architecture/frontend.md)。

### 四工具

| 工具 | 作用 |
|------|------|
| `list_files` | 列出笔记相对路径（只读） |
| `read_file` | 读一篇正文（只读） |
| `search_relative_from_chromadb` | 语义检索已索引片段（只读） |
| `propose_note` | 提交草稿到内存，**不写盘** |

参数、返回值和审批动作：[聊天工具](docs/architecture/chat-tools.md)。系统提示词在 [`src/noteagent/chat/prompts/system.txt`](src/noteagent/chat/prompts/system.txt)。

### 索引

人审写盘、Documents 保存/删除、或 Chat 出处侧栏保存后，按该文件相对路径同步 Chroma（先删旧点再切块）。collection 损坏时仍可手动重建一篇：

```powershell
uv run python scripts/index_notes.py Agent.md
```

切块与查询路径：[检索](docs/architecture/retrieval.md)。脚本说明：[scripts/README.md](scripts/README.md)。

## 快速开始

推荐 Docker：不装 Python、不装本机 PostgreSQL、镜像里已带 MiniLM。聊天仍走外网，必须自己准备 API Key。

1. 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，确认能执行 `docker compose version`（旧环境可用 `docker-compose`）。
2. 克隆本仓库，进入根目录（有 `docker-compose.yml` 的那一层）。
3. 复制环境文件并只改三行：

```powershell
Copy-Item .env.example .env
```

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com
CHAT_MODEL=deepseek-v4-flash
```

账号没有 `deepseek-v4-flash` 时，改成平台上实际可用的模型名。不要改 `EMBEDDING_*`、`HOST`、`DATABASE_URL`：compose 会覆盖。容器自带 Postgres。

4. 启动：

```powershell
docker compose up --build
```

第一次构建会拉镜像并下载嵌入模型，可能要几分钟。入口脚本先 `alembic upgrade head` 再起应用。

5. 浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

Git Bash / macOS / Linux 用 `cp .env.example .env`。排错（端口占用、对话失败、停服务）：[零基础教程](docs/tutorials/zh/getting-started.md)。

## 开发

本机跑应用需要 Python **3.13**、[uv](https://docs.astral.sh/uv/)、PostgreSQL。

```powershell
Copy-Item .env.example .env
# 填 DEEPSEEK_* / CHAT_MODEL，以及：
# DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent
uv sync
uv run alembic upgrade head
uv run python main.py
```

首次把 `EMBEDDING_LOCAL_FILES_ONLY=false`，缓存目录用 `var/models`。测试：

```powershell
uv run pytest -q
```

数据库未升到现行 head 时发聊天会 500。环境变量全表、GBK、Docker 卷：[本机开发](docs/tutorials/zh/local-dev.md)。包地图：[src/noteagent/README.md](src/noteagent/README.md)。给协作者 / Agent 的约束：[CLAUDE.md](CLAUDE.md)。

## 使用说明

| 操作 | 说明 |
|------|------|
| 顶栏 Chat / Documents | 切换主界面；默认 Chat（`GET /`） |
| 新对话 | 聊天左栏底部 |
| 会话三点 | 重命名（行内）、删除（确认框） |
| Enter | 发送；流式进行中不能连发 |
| Shift+Enter | 换行 |
| 审批卡片 | 同意写入 / 拒绝丢弃；部分动作可改文件名 |
| 新建笔记 / 新建文件夹 | Documents 左栏底；选中文件夹则笔记建在其下 |
| 点树中一篇 | 打开编辑 + 预览 |
| 保存 | 工具条，或 Ctrl+S / Cmd+S |
| 未保存圆点 | 顶栏；切篇或离开前会询问 |
| 绿 / 灰芯片 | 已索引 / 未索引；灰芯片可点入库 |
| 拖笔记到文件夹或根 | 确认后移动并改向量路径 |

界面分区与请求：[前端](docs/architecture/frontend.md)。

## 数据放哪

| 位置 | 用途 |
|------|------|
| `notes/` | 正式知识，Markdown 事实源；Docker 时与宿主机 bind |
| PostgreSQL | 会话与气泡；`DATABASE_URL` 前缀须为 `postgresql+psycopg://` |
| `chromadb_persist` | 派生向量；丢了可按文件重建 |
| `var/logs` | Agent / 索引日志；完整 prompt 在这里，不进聊天表 |
| `.env` | 密钥与路径；不要提交。从 `.env.example` 复制 |

不记录你在笔记以外的按键内容。没有账号系统，数据默认只在本机（或你自己的 Docker 卷）。卷说明见 [本机开发](docs/tutorials/zh/local-dev.md)。

## 文档

完整目录：[docs/README.md](docs/README.md)。只想跑起来：[教程索引](docs/tutorials/README.md)。

| 入口 | 内容 |
|------|------|
| [零基础（Docker）](docs/tutorials/zh/getting-started.md) | 从零打开浏览器 |
| [本机开发](docs/tutorials/zh/local-dev.md) | uv、Postgres、测试、环境变量 |
| [架构说明书](docs/architecture/architecture.md) | 现行系统设计；附件在同目录；评测见第 6 节 |
| [评测准则](docs/evaluations/README.md) | 笔记正文 v0.1；工具 / RAG 以后 |
| [evals/](evals/README.md) | 黄金集；离线跑分 `scripts/eval_notes.py`，结果在 `evals/prompt/results/`，不进默认 CI |
| [docs/plans/](docs/plans/README.md) | 已做的实现规格；不要把未落地的 plan 当成现行系统 |

## 项目结构

```text
NoteAgent/
├── main.py                 # 读配置、打日志、启动 uvicorn
├── docker-compose.yml      # 应用 + Postgres
├── Dockerfile
├── pyproject.toml · uv.lock · alembic.ini
├── alembic/                # 会话库迁移
├── notes/                  # 正式 Markdown
├── scripts/                # 按篇索引、API 冒烟
├── tests/                  # 单测 / 集成测（无真实 LLM）
├── evals/                  # 黄金集与 prompt 跑分结果
├── docs/
│   ├── tutorials/          # 层级 × 语言的运行教程
│   ├── architecture/       # 架构书与附件
│   ├── evaluations/        # 评测准则
│   └── plans/              # 实现规格
└── src/noteagent/
    ├── bootstrap/          # Settings、组装 FastAPI
    ├── chat/               # Agent、工具、人审、上下文
    ├── notes/              # 磁盘仓库与 Documents API
    ├── retrieval/          # 切块、Chroma、查询
    ├── db/                 # 会话 ORM
    ├── llm/                # 聊天模型工厂
    ├── observability/      # 日志与 trace
    └── web/                # home.html
```

`var/` 是运行时数据，不入库。
