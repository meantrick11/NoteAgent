# architecture

本目录是**现行系统**的索引。[`architecture.md`](./architecture.md) 是唯一的系统总览，其余文件是附件（参数、公式、表列、检索点、界面、日志），不替代架构书，也不在本目录另写第二份总览。

> 核对日期：2026-09-28，代码提交 `3b1e927`。本目录只描述已经实现的系统；规划中的记录任务、来源管理与多模态材料见 [产品与业务架构](../product/versions/1.5.0/business-architecture.md) 与 [版本路线](../product/versions/1.5.0/roadmap.md)，不代表本目录所述代码已经实现。

## 现行

| 文件 | 内容 | 关联文档 |
|------|------|----------|
| [architecture.md](./architecture.md) | **架构说明书**（简介、背景、总体架构、模块设计、评测、数据架构） | [产品依据](../product/README.md)、[计划](../plans/README.md)、[指南](../guides/README.md)、[评测](../../evals/README.md) |
| [frontend.md](./frontend.md) | 现行 Vue SPA：五个页面、模块职责、两条写盘路径的界面约定与 legacy 回退 | 执行记录 [2026-09-28-vue-frontend-initialization-results.md](../plans/2026-09-28-vue-frontend-initialization-results.md) |
| [chat-tools.md](./chat-tools.md) | Agent 四工具：工作流、参数、人审落盘 | 行为门与轨迹报告见 [evals/README.md](../../evals/README.md) |
| [context-management.md](./context-management.md) | 上下文装配与压缩细则 | 实现切片 [2026-08-26-context-management.md](../plans/2026-08-26-context-management.md) |
| [database.md](./database.md) | PostgreSQL 两表、Store、实例 | 迁移 head 以本文为准 |
| [retrieval.md](./retrieval.md) | 切块、Chroma 点、人写盘后同步、查询路径 | 准则 [rag-quality.md](../../evals/criteria/rag-quality.md)、报告 [rag-v1-report.md](../../evals/reports/rag-v1-report.md)、复盘 [rag-v1-retrospective.md](../../evals/reports/rag-v1-retrospective.md) |
| [observability.md](./observability.md) | 日志三层、Agent/Index 轨迹、业务 logger、输出配置 | 排障入口，见 [guides/zh/local-dev.md](../guides/zh/local-dev.md) |

评测准则与报告已集中到仓库根 [`evals/`](../../evals/README.md)：准则在 `evals/criteria/`，报告与复盘在 `evals/reports/`，黄金集在 `evals/{prompt,rag,agent}/`。架构书第 6 节只做索引，不复制尺子。

## 非现行

已被替代的旧设计不在本目录：正文与替代关系见 [product/archive/](../product/archive/README.md)。

| 旧稿 | 现状 |
|------|------|
| 屏幕/音频采集旧设计 | 归档：[screen-audio-early-design.md](../product/archive/designs/screen-audio-early-design.md)；原 [`DESIGN.md`](./DESIGN.md) 只是跳转页 |
| 入库 Job / URL 源 / 自动索引设想 | 归档：[ingestion-job-early-design.md](../product/archive/designs/ingestion-job-early-design.md)；[`draft-generation.md`](./draft-generation.md) 与 [`../plans/draft-generation.md`](../plans/draft-generation.md) 只是跳转页 |
| 入库设想画布（两个） | 归档：[product/archive/designs/](../product/archive/README.md)。仅由 Cursor 画布宿主渲染，仓库内无构建或运行依赖 |

本目录不写未来能力。新的技术方案与决策写到 [product/](../product/README.md)，落地后再回来同步这里的现状描述。
