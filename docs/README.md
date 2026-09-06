# docs

按阅读顺序串联。`architecture/architecture.md` 是现行系统的全局架构书。专题附件给公式、列清单、工具参数、检索点、界面布局。不要把 `plans/` 或 `DESIGN.md` 当成正在跑的系统。

只想把项目跑起来：见 [tutorials/](tutorials/README.md)，不要从下面的架构附件开始读。

不要写密钥，不要放 `var/` 运行时数据。

## 阅读顺序

1. **[architecture/architecture.md](architecture/architecture.md)** — **架构说明书**：简介、背景、总体架构、数据流、前端/后端（含 Agent 与上下文）/数据库模块设计。
2. **[architecture/frontend.md](architecture/frontend.md)** — 单页布局：Chat 与 Documents 树、编辑预览、拖拽、芯片入库。
3. **[architecture/chat-tools.md](architecture/chat-tools.md)** — 四工具参数、人审动作。
4. **[architecture/context-management.md](architecture/context-management.md)** — 上下文装配公式、压缩、stub。
5. **[architecture/database.md](architecture/database.md)** — PostgreSQL 两表列与实例。
6. **[architecture/retrieval.md](architecture/retrieval.md)** — 切块、Chroma 点、人写盘后同步、查询。
7. **[roadmap/versions.md](roadmap/versions.md)** — V1–V3 版本目标、小版本功能和验收要求。
8. **`src/noteagent/**/README.md`** — 与代码同步的包说明。
9. **[evals/](../evals/README.md)** — 提示词黄金集与人工评分（不进 pytest）。
10. **[plans/](plans/README.md)** — 已做过的实现切片；另含未写入代码的入库 Job 设想。
11. **[architecture/DESIGN.md](architecture/DESIGN.md)** — 屏幕/音频采集旧稿。不要按它写代码。

## 目录

| 目录 | 里面有什么 |
|------|------------|
| [tutorials/](tutorials/README.md) | 运行与开发教程（按层级 × 语言） |
| [architecture/](architecture/README.md) | 架构书与附件（含 frontend）；DESIGN 与画布见该目录说明 |
| [roadmap/](roadmap/versions.md) | V1–V3 产品迭代要求与阶段验收标准 |
| [design/](design/README.md) | 子系统设计文档索引 |
| [plans/](plans/README.md) | 实现规格与入库设想 |
| [decisions/](decisions/README.md) | ADR，目前可空 |
| [evaluations/](evaluations/README.md) | 指针：黄金集在仓库根 [evals/](../evals/README.md) |
| [references/](references/README.md) | 外部摘录，不是契约 |
