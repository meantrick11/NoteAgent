# 零基础：用 Docker 跑起来

目标：在本机浏览器打开 NoteAgent。不需要安装 Python、PostgreSQL 或下载嵌入模型。聊天仍走外网 DeepSeek，所以必须自己准备 API Key。

命令以 **Windows PowerShell** 为例。Git Bash / macOS / Linux 把复制文件改成 `cp .env.example .env` 即可。

## 1. 准备

1. 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，安装后能执行 `docker compose version`（没有 Compose V2 时可用 `docker-compose`）。
2. 到模型提供商申请密钥。默认按 DeepSeek：填 `DEEPSEEK_API_KEY`、接口地址 `DEEPSEEK_API_BASE`、模型名 `CHAT_MODEL`。
3. 克隆本仓库，在资源管理器或终端进入仓库根目录（有 `docker-compose.yml` 的那一层）。

## 2. 配置

```powershell
Copy-Item .env.example .env
```

用编辑器打开 `.env`，**只改这三行**（去掉示例里的空格和占位说明，改成你的真实值）：

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com
CHAT_MODEL=deepseek-v4-flash
```

若你的账号没有 `deepseek-v4-flash`，改成平台上实际可用的模型名。

不要改 `EMBEDDING_*`、`HOST`、`DATABASE_URL`：`docker compose` 会覆盖它们。容器自带 Postgres 和 MiniLM，不用本机数据库。

## 3. 启动

```powershell
docker compose up --build
```

若本机只有旧命令：

```powershell
docker-compose up --build
```

第一次会拉镜像、装依赖、下载嵌入模型，可能要几分钟。日志里出现服务开始监听后，浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

入口脚本会先执行数据库迁移，再启动应用。

停服务：在该终端按 `Ctrl+C`。需要删掉容器时再执行 `docker compose down`（默认不删 Postgres / Chroma 的数据卷）。

## 4. 打开后怎么用

- 左侧是会话列表，可新建、重命名、删除。
- 中间发消息。模型若要写笔记，会出现审批卡片：**同意后才写入** `notes/`。
- 顶栏切到 Documents，可直接管理已落地的 Markdown（一层文件夹）。

宿主机上的 `notes/` 与容器是同一份文件，可用任意编辑器打开。

## 常见问题

**8000 端口被占用。** 改 [`docker-compose.yml`](../../../docker-compose.yml) 里 `app.ports`，例如 `"18000:8000"`，然后访问 `http://127.0.0.1:18000`。

**页面能开，对话失败。** 几乎都是没填或填错 `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` / `CHAT_MODEL`。改 `.env` 后需要重新 `docker compose up`（compose 用 `env_file` 读密钥）。

**本机开发、跑测试、环境变量全表。** 见 [local-dev.md](local-dev.md)。
