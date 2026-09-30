# product

上层文档：**要做什么、采用什么方案、为什么**。当前产品文档基线见 [1.5.0](versions/1.5.0/README.md)，版本管理规则见 [versions/README.md](versions/README.md)。产品要求、版本规划，以及产品与技术设计/决策都放在这里。

现行系统**是什么**见 [architecture/](../architecture/README.md)；某一次具体执行见 [plans/](../plans/README.md)；怎么跑见 [guides/](../guides/README.md)；尺子与证据见 [evals/](../../evals/README.md)。

## 目录职责

| 文件 | 内容 | 状态 |
|---|---|---|
| [versions/1.5.0/](versions/1.5.0/README.md) | 当前产品文档版本线：业务、需求、功能、交付与变更记录 | 现行正文；文档版本独立于软件发布 |
| [backlog.md](backlog.md) | 尚未纳入确认范围的新想法 | 需求池草案 |
| [business-architecture.md](versions/1.5.0/business-architecture.md) | 产品目标、业务对象、共同链路、内容与权限边界 | 有效未来设计（V1 起点已在跑） |
| [roadmap.md](versions/1.5.0/roadmap.md) | V1–V3 的范围、退出标准、验收状态与证据缺口 | 现行说明；判断“完成”的唯一依据 |
| [frontend-architecture.md](versions/1.5.0/frontend-architecture.md) | Vue 页面结构、功能归属及入口演进 | 首轮已实施；顶部四工作入口＋设置齿轮已实施 |
| [settings-architecture.md](versions/1.5.0/settings-architecture.md) | 齿轮入口、设置分类、预留能力与未来个人中心／平台管理边界 | 已实施（2026-09-28）；仅 models／retrieval 开放，其余只预留 ID |
| [README.md](./README.md) | 本索引：上层文档职责、状态口径、设计文档结构约定 | 现行说明 |
| [archive/](./archive/README.md) | 被替代、废弃的设计与画布 | 历史记录；不当作有效要求 |

## 设计和决策写在这里

产品与技术设计、重要取舍的长期主要位置是 `product/`，不是 `plans/`。`plans/` 只放某一次 Agent 执行任务；设计获批不等于功能已完成，现行行为一律读 [architecture/](../architecture/README.md)。

`product/` 下的设计与决策按主题维护：共同业务边界见业务正文，前端方向见 [frontend-architecture.md](./frontend-architecture.md)。不另开 `design/`、`decisions/` 子目录。上两轮的 `docs/design/README.md`、`docs/decisions/README.md` 只有索引职责，其职责已并入本文件。

已有的取舍记录在正文里，不单独抽 ADR：运行时原则见 [architecture.md](../architecture/architecture.md) §1.4；检索选型与代价见 [rag-v1-retrospective.md](../../evals/reports/rag-v1-retrospective.md) 与 [rag-v1-report.md](../../evals/reports/rag-v1-report.md) §6。

### 状态口径

每份上层文档都要能判读处于哪一档，避免把“想做的”当成“做到的”：

| 状态 | 含义 |
|---|---|
| 草案 | 还在讨论，不作为计划依据 |
| 已确认未实施 | 范围和要求已定，尚无实现 |
| 实施中 | 有对应的 [plans/](../plans/README.md) 在执行 |
| 已实施 | 行为已在 [architecture/](../architecture/README.md) 中核对过 |
| 已替代 | 移入 [archive/](./archive/README.md)，写明失效假设与替代入口 |

## 新设计文档的约定结构

后续有效设计按同一结构写，区分已确认方向与尚待确认的细节，不创建没有实际内容的占位正文：

1. 问题与目标；
2. 方案与理由；
3. 替代方案与代价；
4. 边界（不做什么、依赖什么）；
5. 验收要求（可执行的判断条件）；
6. 实施计划链接（`../plans/`）；
7. 落地后的架构链接（`../architecture/`）。

设计一旦被计划采用，改方案要先回来更新本文档，再同步计划——不在执行计划里悄悄改变技术决策。

## 相关

| 想了解 | 去哪 |
|---|---|
| 当前系统结构与行为 | [architecture/architecture.md](../architecture/architecture.md) |
| 某次执行做了什么、到哪一步 | [plans/](../plans/README.md) |
| 怎么跑起来、怎么开发 | [guides/](../guides/README.md) |
| 评测准则、报告与验收证据 | [evals/](../../evals/README.md) |
| 业务术语 | [CONTEXT.md](../../CONTEXT.md) |
