# architecture

[`architecture.md`](./architecture.md) 统领现行全局架构。下面四份是附件（参数、公式、表列、检索点），不替代架构书。

## 现行

| 文件 | 内容 |
|------|------|
| [architecture.md](./architecture.md) | **架构说明书**（简介、背景、总体架构、模块设计、数据架构） |
| [chat-tools.md](./chat-tools.md) | Agent 四工具：工作流、参数、人审落盘 |
| [context-management.md](./context-management.md) | 上下文装配与压缩细则 |
| [database.md](./database.md) | PostgreSQL 两表、Store、实例 |
| [retrieval.md](./retrieval.md) | 切块、Chroma 点、审批后同步、查询路径 |

评测数据不在本目录：仓库根 [`evals/`](../../evals/README.md)。

## 非现行

| 文件 | 内容 |
|------|------|
| [DESIGN.md](./DESIGN.md) | 屏幕/音频采集旧设计，不要按它实现 |
| [draft-generation.md](./draft-generation.md) | 跳转到 [`docs/plans/draft-generation.md`](../plans/draft-generation.md)（入库 Job 设想） |
| `noteagent-architecture.canvas.tsx` | 入库设想画布，不是运行时 |
| `noteagent-system-workflow.canvas.tsx` | 同上 |
