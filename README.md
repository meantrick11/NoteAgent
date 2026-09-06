# NoteAgent

个人学习笔记助手。在浏览器里对话，把值得保留的内容整理成 Markdown 草稿，**你点同意之后**才写入本地 `notes/`，并按该文件更新检索索引。

## 能做什么

- **聊天。** 多会话侧栏、流式回复；历史存在 PostgreSQL。
- **记笔记。** 模型只出提案；聊天里审批，或在 Documents 里直接新建、编辑、移动、删除 Markdown。
- **问旧知识。** 已落地的笔记切块进 Chroma，对话里可按语义检索。

单用户、本机 Web 应用。聊天模型走外网（默认 DeepSeek）；笔记是普通 `.md` 文件，可以自己打开、搬家。

## 板块

| 你想… | 去哪 |
|--------|------|
| 什么都没配，先跑起来 | [教程索引](docs/tutorials/README.md) → 中文 [零基础（Docker）](docs/tutorials/zh/getting-started.md) |
| 在本机改代码、跑测试 | [本机开发](docs/tutorials/zh/local-dev.md) |
| 系统怎么设计 | [架构说明书](docs/architecture/architecture.md) |
| 看应用代码 | [`src/noteagent/`](src/noteagent/README.md) |
| 提示词 / Agent 人工评测 | [`evals/`](evals/README.md) |
| `docs/` 里还有哪些目录 | [文档总目录](docs/README.md) |

## 仓库一览

| 路径 | 作用 |
|------|------|
| [`src/noteagent/`](src/noteagent/README.md) | 应用代码 |
| [`notes/`](notes/README.md) | 正式 Markdown |
| [`docs/`](docs/README.md) | 架构、教程、实现规格 |
| [`tests/`](tests/README.md) | 单测 / 集成测（不调真实 LLM） |
| [`evals/`](evals/README.md) | 黄金集，不进默认 CI |
| [`scripts/`](scripts/README.md) | 索引、API 冒烟 |
| [`main.py`](main.py) | 进程入口 |
