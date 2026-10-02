# NoteAgent

个人学习笔记助手。本机 Web · Docker 或 uv · 人审后写 Markdown。

产品远景是把对话、网页、视频与会议等内容整理为可复用材料；当前交付以聊天笔记闭环为起点。业务边界见 [产品与业务架构](../NoteAgent-docs/docs/01-business/BIZ-001-业务愿景与材料管理.md)，未来能力与验收见 [版本路线](../NoteAgent-docs/docs/02-requirements/REQ-CATALOG-产品能力与验收要求.md)。

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
| 人审写盘 | 模型不能直接改文件。`propose_note` 将待审草稿保存到会话；同意后才 `create` / `append` / `replace` / `delete`。细节：[聊天工具](docs/02-api/chat-tools.md) |
| 五个页面 | 顶部固定 **Home → Assistant → Records → Library** 四个工作入口，右上角齿轮进入 **Settings**。Assistant 管会话与问答，Library 管磁盘上的笔记，Settings 分「模型与连接」「检索与索引」两类。布局：[前端](docs/03-modules/frontend/frontend.md) |
| 一层目录 | 允许 `notes/Folder/Note.md`，禁止两层和 `..`。根下 `notes/*.md` 为未进文件夹的篇 |
| 派生检索 | Chroma 由 Markdown 重建。索引失败不回滚已写入的笔记。现行配置是 `intfloat/multilingual-e5-small` + 章节感知切块，collection 存配置指纹，改配置必须重建。[检索](docs/03-modules/retrieval/retrieval.md)、[为什么这样选](evals/reports/rag-v1-retrospective.md) |

三条运行时原则：LLM 只出提案；磁盘只走人类操作（聊天审批、Library、或 Assistant 引用面板保存）；聊天气泡不画工具过程。

## 功能说明

### 聊天

左侧是会话列表（PostgreSQL）。点会话加载气泡；底栏输入，Enter 发送、Shift+Enter 换行。流式回复走 `POST /chat`（SSE）。同一时刻只能发一句。

气泡只有 `user` 和最终 `assistant`（与输入框同宽对齐）。`list_files` / 检索 / 提案等工具调用给模型和日志，不进侧栏。点回复里的 ① 可在右侧改该笔记并保存（`PUT /notes`，与 Documents 相同重索引）；无预览、无删除。

跨回合给模型的上下文 = 摘要水位线之后的 Persistent（含 tool stub）+ `running_summary` + 当前这一轮内存里的 Runtime。公式与截断：[上下文管理](docs/03-modules/chat/context-management.md)。会话表：[数据库](docs/01-architecture/database.md)。

### 待审草稿

模型认为该记笔记时，会调用 `propose_note`，右侧面板切到「待审批草稿」：正文可编辑并「保存草稿」（只改待审状态），确认后「同意追加/覆盖/删除/新建」或「拒绝」。`create`、`append` 可以改目标文件或改成新建。只有 `POST /chat/review` 成功后才写 `notes/`。拒绝则丢弃该草稿，不改磁盘、不改向量。

### Library（原 Documents）

Library 页：左树、右编辑器 + Markdown 预览。保存、新建、移动、删除都是人写盘，不经过 Agent。保存后按该相对路径删旧向量再整篇索引。树上看「已索引 / 未索引」芯片（未索引可点入库）。只拖笔记、不拖文件夹；一层目录。拖拽、芯片、弹窗细节见 [前端](docs/03-modules/frontend/frontend.md)。

### 四工具

| 工具 | 作用 |
|------|------|
| `list_files` | 列出笔记相对路径（只读） |
| `read_file` | 读一篇正文（只读） |
| `search_relative_from_chromadb` | 语义检索已索引片段（只读） |
| `propose_note` | 持久化会话待审草稿，**不修改正式笔记** |

参数、返回值和审批动作：[聊天工具](docs/02-api/chat-tools.md)。系统提示词在 [`src/noteagent/chat/prompts/system.txt`](src/noteagent/chat/prompts/system.txt)。

### 索引

人审写盘、Documents 保存/删除、或 Chat 出处侧栏保存后，按该文件相对路径同步 Chroma（先删旧点再切块）。collection 损坏时仍可手动重建一篇：

```powershell
uv run python scripts/index_notes.py Agent.md
```

输入框下侧靠右的**向量入口**可以切换本地向量模型，也可以在索引丢失/配置不符时点「重建并修复」。索引用**身份指纹**（模型 + 权重快照 + 分块策略与大小 + 标题前缀 + 编码指令 + 正文规范化版本）标识，指纹不同的索引各有自己的 collection，所以改了分块配置不需要先删旧库；丢失的索引会如实报为不可用，不会用一个空 collection 冒充。重建期间不能发送消息或写笔记（后端也拒绝），旧索引保留到新索引校验通过。

切块与查询路径：[检索](docs/03-modules/retrieval/retrieval.md)。脚本说明：[scripts/README.md](scripts/README.md)。

## 快速开始

推荐 Docker：不装 Python、不装本机 PostgreSQL、镜像里已带向量模型 `intfloat/multilingual-e5-small`。聊天仍走外网，必须自己准备 API Key。

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

第一次构建会拉镜像并下载嵌入模型，可能要几分钟。镜像里有一个 Node 阶段先把 Vue 前端编译好，
再拷进 Python 镜像；运行容器里没有 Node，也不会多开端口。入口脚本先 `alembic upgrade head` 再起应用。

5. 浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

Git Bash / macOS / Linux 用 `cp .env.example .env`。排错（端口占用、对话失败、停服务）：[零基础教程](docs/04-ops/getting-started.md)。

## 开发

本机跑应用需要 Python **3.13**、[uv](https://docs.astral.sh/uv/)、PostgreSQL、Node **20.19+ / 22.12+**。

```powershell
Copy-Item .env.example .env
# 填 DEEPSEEK_* / CHAT_MODEL，以及：
# DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent
uv sync
uv run alembic upgrade head
npm --prefix frontend ci
npm --prefix frontend run build
uv run python main.py
```

界面默认走 Vue，产物在 `src/noteagent/web/dist/`；**没构建过时页面返回 503 并给出构建提示**。
想先用旧页面：设 `FRONTEND_MODE=legacy`。前端开发（Vite 热更新、类型检查、单测与 e2e）：
[frontend/README.md](frontend/README.md)。

首次把 `EMBEDDING_LOCAL_FILES_ONLY=false`，缓存目录用 `var/models`。测试：

```powershell
uv run pytest -q
npm --prefix frontend run type-check
npm --prefix frontend run test:unit
npm --prefix frontend run test:e2e
```

数据库未升到现行 head 时发聊天会 500。环境变量全表、GBK、Docker 卷：[本机开发](docs/00-overview/local-dev.md)。包地图：[src/noteagent/README.md](src/noteagent/README.md)。给协作者 / Agent 的约束：[CLAUDE.md](CLAUDE.md)。

## 使用说明

| 操作 | 说明 |
|------|------|
| 顶部五项 | Home / Assistant / Records / Library / Settings；默认 Home（`GET /`），旧地址 `/documents` 落到 Library |
| 新对话 | 聊天左栏底部 |
| 会话三点 | 重命名（行内）、删除（确认框） |
| Enter | 发送；流式进行中不能连发 |
| Shift+Enter | 换行 |
| 右侧草稿面板 | 编辑正文并保存草稿；同意写入 / 拒绝丢弃；create、append 可改目标文件 |
| 新建笔记 / 新建文件夹 | Library 左栏底；选中文件夹则笔记建在其下 |
| 点树中一篇 | 打开编辑 + 预览 |
| 保存 | 工具条，或 Ctrl+S / Cmd+S |
| 未保存圆点 | 顶栏；切篇或离开前会询问 |
| 绿 / 灰芯片 | 已索引 / 未索引；灰芯片可点入库 |
| 拖笔记到文件夹或根 | 确认后移动并改向量路径 |
| 输入框下「聊天：… ▾」 | 新增 / 编辑 / 启用 / 删除聊天配置。「保存」只存草稿，「保存并启用」才更换正在运行的客户端；**当前启用的那条不能直接编辑或删除**，先启用另一条 |
| 输入框下「向量：… ▾」 | 选本地已有向量模型「重建并切换」；当前模型索引不可用时按钮变成「重建并修复」 |

界面分区与请求：[前端](docs/03-modules/frontend/frontend.md)。

## 数据放哪

| 位置 | 用途 |
|------|------|
| `notes/` | 正式知识，Markdown 事实源；Docker 时与宿主机 bind |
| PostgreSQL | 会话与气泡；`DATABASE_URL` 前缀须为 `postgresql+psycopg://` |
| `chromadb_persist` | 派生向量；丢了可按文件重建 |
| `var/logs` | Agent / 索引日志；完整 prompt 在这里，不进聊天表 |
| `var/model_settings/settings.json` | 界面上保存的聊天配置与向量选择。**界面上填写的 API Key 明文在这里**（未加密，`chmod 600` 尽力而为）；`.env` 的 Key 不被复制进来 |
| `.env` | 密钥与路径；不要提交。从 `.env.example` 复制 |

备份或迁移：直接备份 `var/model_settings` 目录（连同 `notes/` 与 Chroma 目录）。移除某条凭据只有两条路——界面上「清除已保存的 Key」或删除该配置；删除配置是唯一会连凭据一起移除的操作。Docker 下该目录必须挂持久卷，否则容器重建等于丢凭据。

不记录你在笔记以外的按键内容。没有账号系统，数据默认只在本机（或你自己的 Docker 卷）。卷说明见 [本机开发](docs/00-overview/local-dev.md)。

## 文档

完整目录：[docs/README.md](docs/README.md)。只想跑起来：[教程索引](docs/00-overview/README.md)。

| 入口 | 内容 |
|------|------|
| [零基础（Docker）](docs/04-ops/getting-started.md) | 从零打开浏览器 |
| [本机开发](docs/00-overview/local-dev.md) | uv、Postgres、测试、环境变量 |
| [架构说明书](docs/01-architecture/architecture.md) | **现行系统的阅读主线**：模块、数据流、关键决策与代码落点 |
| [产品与业务架构](../NoteAgent-docs/docs/01-business/BIZ-001-业务愿景与材料管理.md) | 记录与复用场景、业务对象、整理方案及目标边界 |
| [版本路线](../NoteAgent-docs/docs/02-requirements/REQ-CATALOG-产品能力与验收要求.md) | 分阶段交付、当前证据缺口与验收要求 |
| [产品与技术设计](../NoteAgent-docs/README.md) | 上层设计、技术决策与状态口径 |
| [实现计划与执行记录](docs/05-records/plans/README.md) | 某一版怎么做、做到哪一步；计划里的“待实现”不是现状 |
| [评测准则与报告](evals/README.md) | 准则在 `evals/criteria/`，报告与复盘在 `evals/reports/`，黄金集与运行结果在同目录 |
| [归档设计](docs/05-records/archive/README.md) | 已被替代的旧设计：屏幕采集、入库 Job 设想及其画布 |

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
├── frontend/               # Vue 3 + Vite 前端工程；产物写到 src/noteagent/web/dist/
├── tests/                  # 单测 / 集成测（无真实 LLM）
├── evals/                  # 评测：criteria/ 准则、reports/ 报告、prompt|rag|agent 数据
├── docs/
│   ├── README.md           # 研发文档导航；版本随代码 Tag
│   ├── 00-overview/        # 入门与开发
│   ├── 01-architecture/    # 当前架构与数据库
│   ├── 02-api/             # 接口与工具契约
│   ├── 03-modules/         # chat / frontend / retrieval 专题
│   ├── 04-ops/             # 部署与可观测性
│   ├── 05-records/         # 计划、结果、历史设计
│   ├── 06-releases/        # 代码版本发布记录
│   ├── 07-assets/          # 附件与历史画布
│   ├── references/         # 用户维护的个人记录，非契约
│   └── roadmap/            # 用户代码解析，保留例外
└── src/noteagent/
    ├── bootstrap/          # Settings、组装 FastAPI
    ├── chat/               # Agent、工具、人审、上下文
    ├── notes/              # 磁盘仓库与 Documents API
    ├── retrieval/          # 切块、Chroma、查询
    ├── db/                 # 会话 ORM
    ├── llm/                # 聊天模型工厂
    ├── observability/      # 日志与 trace
    └── web/                # 页面路由、SPA 产物与旧模板（回退用）
```

`var/` 是运行时数据，不入库。业务、需求、目标架构及 CR/ADR 在同级 [NoteAgent-docs](../NoteAgent-docs/README.md) 独立维护；代码内实现说明随代码 Tag。
