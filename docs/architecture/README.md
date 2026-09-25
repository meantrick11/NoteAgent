# architecture

[`architecture.md`](./architecture.md) 统领现行全局架构。下面是附件（参数、公式、表列、检索点、界面、日志），不替代架构书。

上层业务见 [产品与业务架构](../product/business-architecture.md)，阶段目标与验收见 [版本路线](../roadmap/versions.md)。未来的记录任务、来源管理和多模态材料不代表本目录所述代码已经实现。

## 现行

| 文件 | 内容 |
|------|------|
| [architecture.md](./architecture.md) | **架构说明书**（简介、背景、总体架构、模块设计、评测、数据架构） |
| [frontend.md](./frontend.md) | 单页 Chat / Documents 布局、树、拖拽、芯片、弹窗 |
| [chat-tools.md](./chat-tools.md) | Agent 四工具：工作流、参数、人审落盘 |
| [context-management.md](./context-management.md) | 上下文装配与压缩细则 |
| [database.md](./database.md) | PostgreSQL 两表、Store、实例 |
| [retrieval.md](./retrieval.md) | 切块、Chroma 点、人写盘后同步、查询路径 |
| [observability.md](./observability.md) | 日志三层、Agent/Index 轨迹、业务 logger、输出配置 |

评测准则：[docs/evaluations/](../evaluations/README.md)。黄金集不在本目录：仓库根 [`evals/`](../../evals/README.md)。

## 复盘

| 文件 | 内容 |
|------|------|
| [rag-v1-retrospective.md](./rag-v1-retrospective.md) | 2026-09-25 检索质量工作：遇到的问题（产品侧 7 条、评测侧 6 条）、做法、结果、不足与后续触发条件。数字与失败样例见 [rag-v1-report.md](../evaluations/rag-v1-report.md) |

复盘不是规格：现行实现以本目录的架构书与附件为准。

## 非现行

| 文件 | 内容 |
|------|------|
| [DESIGN.md](./DESIGN.md) | 屏幕/音频采集旧设计，不要按它实现 |
| [draft-generation.md](./draft-generation.md) | 跳转到 [`docs/plans/draft-generation.md`](../plans/draft-generation.md)（入库 Job 设想） |
| `noteagent-architecture.canvas.tsx` | 入库设想画布，不是运行时 |
| `noteagent-system-workflow.canvas.tsx` | 同上 |
