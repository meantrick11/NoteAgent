# docs

先读业务目标与版本交付，再按需要了解现行实现。`product/business-architecture.md` 描述上层业务，`roadmap/versions.md` 定义阶段范围与验收，`architecture/architecture.md` 描述当前系统。业务目标和计划中的未来能力不代表已经实现。

只想把项目跑起来：见 [tutorials/](tutorials/README.md)，不要从下面的架构附件开始读。

不要写密钥，不要放 `var/` 运行时数据。

## 阅读顺序

1. **[产品与业务架构](product/business-architecture.md)** — 用户场景、共同链路、来源/草稿/材料、定制边界、状态和演进方向。
2. **[业务术语](../CONTEXT.md)** — 来源、记录任务、采集会话、整理方案与材料的统一含义。
3. **[版本路线](roadmap/versions.md)** — V1–V3 做到什么程度、如何验收、当前证据缺口；产品里程碑不等同于包版本。
4. **[现行架构](architecture/architecture.md)** — 当前系统结构、数据流、模块设计、评测与数据架构。
5. **[前端](architecture/frontend.md)**、**[聊天工具](architecture/chat-tools.md)** — 当前界面和人审动作。
6. **[上下文](architecture/context-management.md)**、**[数据库](architecture/database.md)** — 当前装配公式、压缩与数据表。
7. **[检索](architecture/retrieval.md)**、**[可观测性](architecture/observability.md)** — 当前索引、查询和日志。
8. **[评测准则](evaluations/README.md)** 与 **[evals/](../evals/README.md)** — 准则、黄金集与跑分结果；评测结果用于版本验收。
9. **[实现计划](plans/README.md)** 与 `src/noteagent/**/README.md` — 具体切片及代码包说明；计划状态要单独核对。

历史参考：[屏幕/音频旧稿](architecture/DESIGN.md)、[入库 Job 旧设想](plans/draft-generation.md)。其中与上层业务不一致的假设已在入口标注，不作为新功能规格。根目录 `TODO.md` 是长期学习清单，不作为产品版本状态表。



## 目录


| 目录                                      | 里面有什么                                                         |
| --------------------------------------- | ------------------------------------------------------------- |
| [tutorials/](tutorials/README.md)       | 运行与开发教程（按层级 × 语言）                                             |
| [product/](product/business-architecture.md) | 上层业务架构：场景、对象、链路、边界与演进 |
| [architecture/](architecture/README.md) | 架构书与附件（含 frontend）；DESIGN 与画布见该目录说明                           |
| [roadmap/](roadmap/versions.md)         | V1–V3 产品迭代要求与阶段验收标准                                           |
| [design/](design/README.md)             | 子系统设计文档索引                                                     |
| [plans/](plans/README.md)               | 实现规格与入库设想                                                     |
| [decisions/](decisions/README.md)       | ADR，目前可空                                                      |
| [evaluations/](evaluations/README.md)   | 评测准则（笔记正文现行 v0.2；旧题仍走 v0.1；工具 / RAG 以后）；黄金集在 [evals/](../evals/README.md) |
| [references/](references/README.md)     | 外部摘录，不是契约                                                     |


