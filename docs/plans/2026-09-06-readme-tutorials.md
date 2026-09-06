# 首页 README 与 tutorials 目录

> 文档规格。不改启动逻辑。现行系统仍以 [../architecture/architecture.md](../architecture/architecture.md) 为准。

**Goal:** 根 README 做短首页（介绍 + 板块入口）。运行/开发教程进 `docs/tutorials/`，按层级 × 语言索引。本次只写中文「零基础 Docker」和「本机开发」。

## 职责

| 入口 | 管什么 | 不管什么 |
|------|--------|----------|
| 根 `README.md` | 产品是什么、能做什么、仓库板块 | 逐步安装命令；架构附件阅读顺序 |
| `docs/tutorials/` | 怎么跑、怎么配环境；层级 × 语言 | 系统设计、表结构、工具参数 |
| `docs/architecture/` | 现行系统怎么设计 | 安装教程 |
| `docs/README.md` | `docs/` 各目录是干什么的 | 仓库首页 |

## 教程路径约定

`docs/tutorials/<lang>/<slug>.md`。层级写在 `docs/tutorials/README.md` 表里。本次不建空的 `en/`。

## 文件

| 文件 | 改动 |
|------|------|
| [`README.md`](../../README.md) | 短介绍 + 板块入口 |
| [`docs/tutorials/README.md`](../tutorials/README.md) | 层级 × 语言索引 |
| [`docs/tutorials/zh/getting-started.md`](../tutorials/zh/getting-started.md) | 零基础 Docker |
| [`docs/tutorials/zh/local-dev.md`](../tutorials/zh/local-dev.md) | 本机 uv / Postgres |
| [`docs/README.md`](../README.md) | 目录表加 `tutorials/` |
| [`.env.example`](../../.env.example) | embedding 默认 `var/models`；本机可下载 |

## 不在范围

不改 Dockerfile / compose。不写第二份根 README。不提交 git。
