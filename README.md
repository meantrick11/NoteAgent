# NoteAgent

个人学习笔记助手。本机 Web · Docker 或 uv · 人审后写 Markdown。

产品远景是把对话、网页、视频与会议等内容整理为可复用材料；当前交付以聊天笔记闭环为起点。业务语言见 [业务术语](CONTEXT.md)，当前能力见 [功能说明](#功能说明)，实施证据见 [验收记录](docs/05-records/plans/2026-10-04-checkpoint-shadow-git-completion-results.md)。

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
| 指定网页读取（V2.4，待验收） | 用户给出固定 URL 后，Agent 逐个读取并提取正文；按用户意图回答或生成待审草稿。获取失败、登录验证和截断会告知用户；网页正文不另存本地文件。细节：[聊天工具](docs/02-api/chat-tools.md)、[执行结果](docs/05-records/plans/2026-10-11-v24-user-url-reading-results.md) |
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

模型认为该记笔记时，会调用 `propose_note`，右侧面板切到「待审批草稿」：正文可编辑并「保存草稿」（只改待审状态），确认后「同意追加/覆盖/删除/新建」或「拒绝」。新建草稿点击顶部笔记名更名；底部直接提供同意、拒绝和追加到笔记，追加需选择目标再确认。只有 `POST /chat/review` 成功后才写 `notes/`。拒绝则丢弃该草稿，不改磁盘、不改向量。

### Library（原 Documents）

Library 页：左树、右编辑器 + Markdown 预览。保存、新建、移动、删除都是人写盘，不经过 Agent。保存后按该相对路径删旧向量再整篇索引。树上看「已索引 / 未索引」芯片（未索引可点入库）。只拖笔记、不拖文件夹；一层目录。拖拽、芯片、弹窗细节见 [前端](docs/03-modules/frontend/frontend.md)。

### 聊天工具

| 工具 | 作用 |
|------|------|
| `list_files` | 列出笔记相对路径（只读） |
| `read_file` | 读一篇正文（只读） |
| `search_relative_from_chromadb` | 语义检索已索引片段（只读） |
| `read_webpage` | 读取用户给定的单个 URL，返回正文与获取状态（只读；生产装配启用） |
| `propose_note` | 持久化会话待审草稿，**不修改正式笔记** |

参数、返回值和审批动作：[聊天工具](docs/02-api/chat-tools.md)。系统提示词在 [`src/NoteAgent/Modules/Chat/Agent/SystemPrompts/system.txt`](src/NoteAgent/Modules/Chat/Agent/SystemPrompts/system.txt)。

网页笔记的 `## 来源` 栏随草稿一起预览，审批通过后才写入正式笔记。首版只读取用户提供的 URL，不按主题搜索网页；V2.4 已合入 `main`，仍需 PostgreSQL 集成补验和真实模型网页笔记成稿验收。

### 索引

人审写盘、Documents 保存/删除、或 Chat 出处侧栏保存后，按该文件相对路径同步 Chroma（先删旧点再切块）。collection 损坏时仍可手动重建一篇：

```powershell
uv run python Scripts/IndexNotes.py Agent.md
```

输入框下侧靠右的**向量入口**可以切换本地向量模型，也可以在索引丢失/配置不符时点「重建并修复」。索引用**身份指纹**（模型 + 权重快照 + 分块策略与大小 + 标题前缀 + 编码指令 + 正文规范化版本）标识，指纹不同的索引各有自己的 collection，所以改了分块配置不需要先删旧库；丢失的索引会如实报为不可用，不会用一个空 collection 冒充。重建期间不能发送消息或写笔记（后端也拒绝），旧索引保留到新索引校验通过。

切块与查询路径：[检索](docs/03-modules/retrieval/retrieval.md)。脚本说明：[Scripts/README.md](Scripts/README.md)。

## 快速开始

推荐 Docker：不装 Python、不装本机 PostgreSQL、镜像里已带向量模型 `intfloat/multilingual-e5-small`。聊天仍走外网，必须自己准备 API Key。

1. 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，确认能执行 `docker compose version`（旧环境可用 `docker-compose`）。
2. 克隆本仓库，进入根目录（有 `docker-compose.yml` 的那一层）。
3. 复制环境文件（Docker 下不需要提前填模型 Key）：

```powershell
Copy-Item .env.example .env
```

模型配置保存在 PostgreSQL，启动后在 **Settings → 模型与连接** 添加：选择 Provider、填写模型名/Base URL/API Key，点“测试”通过后“保存并启用”。不要改 `EMBEDDING_*`、`HOST`、`DATABASE_URL`：compose 会覆盖。容器自带 Postgres。

4. 启动：

```powershell
docker compose up --build
```

第一次构建会拉镜像并下载嵌入模型，可能要几分钟。镜像里有一个 Node 阶段先把 Vue 前端编译好，
再拷进 Python 镜像；运行容器里没有 Node，也不会多开端口。入口脚本先 `alembic upgrade head` 再起应用。

5. 浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。首次启动没有启用模型时页面可用，聊天接口会返回 503；到 Settings 添加并启用模型后即可对话。

Git Bash / macOS / Linux 用 `cp .env.example .env`。排错（端口占用、对话失败、停服务）：[零基础教程](docs/04-ops/getting-started.md)。

## 开发

本机跑应用需要 Python **3.13**、[uv](https://docs.astral.sh/uv/)、PostgreSQL、Node **20.19+ / 22.12+**。

```powershell
Copy-Item .env.example .env
# 填 DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent
# 模型配置不写 .env：启动后在 Settings → 模型与连接 添加、测试并启用
uv sync
uv run alembic upgrade head
npm --prefix frontend ci
npm --prefix frontend run build
uv run python main.py
```

界面默认走 Vue，产物在 `src/NoteAgent/WebFrontend/dist/`；**没构建过时页面返回 503 并给出构建提示**。
想先用旧页面：设 `FRONTEND_MODE=legacy`。前端开发（Vite 热更新、类型检查、单测与 e2e）：
[frontend/README.md](frontend/README.md)。

首次把 `EMBEDDING_LOCAL_FILES_ONLY=false`，缓存目录用 `var/models`。测试：

```powershell
uv run pytest -q
npm --prefix frontend run type-check
npm --prefix frontend run test:unit
npm --prefix frontend run test:e2e
```

数据库未升到现行 head 时发聊天会 500。环境变量全表、GBK、Docker 卷：[本机开发](docs/00-overview/local-dev.md)。包地图：[src/NoteAgent/README.md](src/NoteAgent/README.md)。给协作者 / Agent 的约束：[CLAUDE.md](CLAUDE.md)。

## 使用说明

| 操作 | 说明 |
|------|------|
| 主导航与设置 | Home / Assistant / Records / Library 四个入口；Settings 从右上角齿轮进入。默认 Home（`GET /`），旧地址 `/documents` 落到 Library |
| 新对话 | 聊天左栏底部 |
| 会话三点 | 重命名（行内）、删除（确认框） |
| Enter | 发送；流式进行中不能连发 |
| Shift+Enter | 换行 |
| 右侧草稿面板 | 顶部点击新建笔记名更名；保存草稿只保存状态，同意才写入；追加到笔记单独选择目标 |
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
| PostgreSQL | checkpoint 完整历史、压缩摘要、草稿与执行状态，以及会话元数据和恢复日志；`DATABASE_URL` 前缀须为 `postgresql+psycopg://` |
| `var/notes_history` | 独立影子 Git，记录笔记材料版本；消息回退通过选择性恢复保留无关改动 |
| `chromadb_persist` | 派生向量；丢了可按文件重建 |
| `var/logs` | Agent / 索引日志；完整 prompt 在这里，不进聊天表 |
| PostgreSQL 模型表 | 模型配置、Provider/端点、API Key 与能力验证证据。Key 不进入 HTTP 响应或日志；**数据库备份包含凭据**，必须按密钥材料保护 |
| `var/model_settings` | Retrieval 的 embedding 状态；迁移前旧模型配置备份 `settings.pre-db.json`（0600），仅遗留导入器读取 |
| `.env` | 引导与基础设施配置（数据库、路径、端口）；不要提交。从 `.env.example` 复制 |

备份或迁移：备份 PostgreSQL（含 checkpoint、模型配置与凭据）、`notes/`、`var/notes_history` 和 `var/model_settings`；Chroma 可按正文重建。移除某条凭据只有两条路——界面上「清除已保存的 Key」或删除该配置；删除配置是唯一会连凭据一起移除的操作。数据库备份和 `settings.pre-db.json` 含明文凭据，分享前必须脱敏。

不记录你在笔记以外的按键内容。没有账号系统，数据默认只在本机（或你自己的 Docker 卷）。卷说明见 [本机开发](docs/00-overview/local-dev.md)。

## 文档

完整目录：[docs/README.md](docs/README.md)。只想跑起来：[教程索引](docs/00-overview/README.md)。

| 入口 | 内容 |
|------|------|
| [零基础（Docker）](docs/04-ops/getting-started.md) | 从零打开浏览器 |
| [本机开发](docs/00-overview/local-dev.md) | uv、Postgres、测试、环境变量 |
| [架构说明书](docs/01-architecture/architecture.md) | **现行系统的阅读主线**：模块、数据流、关键决策与代码落点 |
| [业务术语](CONTEXT.md) | 来源、记录任务、笔记材料等业务概念 |
| [会话持久化与续接](docs/03-modules/chat/checkpoint-resume.md) | PostgreSQL checkpoint、草稿保存、执行续接及版本冲突 |
| [笔记与整体回退](docs/03-modules/recovery/recovery.md) | 影子 Git、共享冲突拦截与按文件 RAG 修复 |
| [本轮验收记录](docs/05-records/plans/2026-10-04-checkpoint-shadow-git-completion-results.md) | 已验证行为、测试结果、故障演练及剩余限制 |
| [实现计划与执行记录](docs/05-records/plans/README.md) | 某一版怎么做、做到哪一步；计划里的“待实现”不是现状 |
| [评测准则与报告](evals/README.md) | 准则在 `evals/criteria/`，报告与复盘在 `evals/reports/`，黄金集与运行结果在同目录 |
| [归档设计](docs/05-records/archive/README.md) | 已被替代的旧设计：屏幕采集、入库 Job 设想及其画布 |

## 项目结构

```text
NoteAgent/
├─ main.py                    后端入口
├─ src/NoteAgent/
│  ├─ AppBootstrap/           配置、装配、生命周期
│  ├─ Modules/                按业务能力组织的后端模块
│  ├─ Common/                 数据库、日志、共享访问与 HTTP 公共能力
│  └─ WebFrontend/            已构建页面托管
├─ frontend/                  Vue 源码、测试和构建配置
├─ Tests/                     Python 单元与集成测试
├─ alembic/                   全应用数据库迁移链
├─ Scripts/                   可直接运行的维护脚本
├─ Tools/                     可复用内部工具
├─ evals/                     评测数据、准则与报告
├─ docs/                      当前实现文档与执行记录
├─ docker/                    容器入口脚本
├─ notes/                     本地正式笔记，不提交正文
├─ uploads/                   本地来源文件，不提交
├─ chromadb_persist/          本地向量索引，不提交
└─ var/                       运行日志、缓存、配置和笔记版本
```

职责、目录及旧名映射见 [源码导航](src/NoteAgent/README.md)。自有 Python 包和文件统一使用大驼峰；框架特殊文件保留固定名称。类和函数名沿用现有接口。Vue 构建输出在 src/NoteAgent/WebFrontend/dist。
