# docs

文档入口。正式文档按四个目录组织，评测标准与证据集中在仓库根 [`evals/`](../evals/README.md)。

**主线是读现行系统**：[architecture/architecture.md](architecture/architecture.md) —— 它描述已经实现的代码，其余文档围绕它给出依据、计划和证据。

三条阅读路径：

1. **理解当前系统** → [现行架构](architecture/architecture.md) → [架构附件](architecture/README.md) → [操作指南](guides/README.md)。先看现在是什么，再看怎么跑。
2. **了解产品与规划** → [产品文档 1.5.0](product/versions/1.5.0/README.md) → [产品与业务架构](product/versions/1.5.0/business-architecture.md) → [版本路线](product/versions/1.5.0/roadmap.md)。做什么、边界在哪、每版做到什么程度、还缺什么证据。
3. **继续开发** → [产品与技术设计](product/README.md) → [执行计划](plans/README.md) → [评测标准与报告](../evals/README.md)。先确认方案与依据，再看执行记录与尺子。

只想把项目跑起来：见 [guides/](guides/README.md)，不要从架构附件开始读。

不要写密钥，不要放 `var/` 运行时数据。

## 四个主要目录

一个事实只保留一个主要维护位置，其他文档链接过去，不复制。

| 目录 | 回答什么 | 状态口径 |
|---|---|---|
| [architecture/](architecture/README.md) | **现在是什么**：已实现的系统结构、模块、数据流 | 现行说明；头部记核对日期与依据提交 |
| [product/](product/README.md) | **要做什么、采用什么方案、为什么**：产品目标、路线图、设计与技术决策 | 草案 / 已确认未实施 / 实施中 / 已实施 / 已替代 |
| [plans/](plans/README.md) | **本次 Agent 如何执行、执行到了哪里** | 执行计划：执行中 / 已完成 / 历史参考 |
| [guides/](guides/README.md) | **如何使用、操作和开发** | 现行步骤，过时即修订 |

## 其它位置

| 位置 | 职责 | 说明 |
|---|---|---|
| [`evals/`](../evals/README.md) | 评测准则（`criteria/`）、报告与复盘（`reports/`）、黄金集与运行结果 | 评测的唯一主要入口；`results/` 是运行证据，不改写 |
| [references/](references/README.md) | 外部摘录与个人记录 | **非契约**，且是受保护的个人目录，本轮未改动 |
| [product/archive/](product/archive/README.md) | 被替代、废弃的设计与画布 | 历史记录；每份写明失效假设与替代入口 |
| [roadmap/](roadmap/版本1.1代码解析.md) | 仅保留用户未跟踪的代码讲解 | **兼容例外**：不是正式结构，内容由用户维护，不当作现行说明 |
| [CONTEXT.md](../CONTEXT.md) | 业务术语 | 只定义词义，不重复业务全貌或阶段状态 |

根目录 [`TODO.md`](../TODO.md) 是个人长期学习清单，不是产品版本状态表。

四个目录之外的旧路径（`architecture/{DESIGN,draft-generation}.md`、`plans/draft-generation.md`、`roadmap/`）只是兼容入口或个人文件所在处，不作为新内容的放置位置。

## 冲突怎么判

- **当前行为**由代码与验证说明（[architecture/](architecture/README.md) + 测试/报告）；**目标**由有效需求说明（[product/](product/README.md) + [product/roadmap.md](product/roadmap.md)）；**历史成绩**保持原 run 身份（[evals/reports/](../evals/reports/)）。
- 差异不能靠静默改需求或改历史结果来掩盖。发现实现与有效要求不一致：记录缺口与依据，改需求要走验收流程。
- 实现存在 ≠ 已验证。实现、测试存在、执行通过是三种证据。
- 报告里的数字要能定位到 run 与配置；勘误只改被证明写错的值，保留原运行日期与成绩归属。
- 设计获批不代表功能完成；改方案先更新 [product/](product/README.md)，再同步计划，不在执行计划里悄悄改变技术决策。

## 文档头部约定

活动入口与本次修订过的文档按需加简短头部；不要求批量改写历史文件。

| 文档类型 | 头部写什么 |
|---|---|
| 现行说明（architecture） | 状态、核对日期、依据提交 |
| 产品与设计（product） | 状态档位、适用版本、依据与替代关系 |
| 执行计划（plans） | 需求/设计依据、执行状态、验证入口；逐项区分实现 / 已验证 / 跳过 / 未完成 |
| 评测报告（evals/reports） | 交付日期、run 身份、配置与提交；勘误单列 |
| 归档（product/archive） | 历史状态、核对日期、失效假设、有效替代入口 |

## 维护动作

- 行为变更后同步 [architecture/](architecture/README.md)；执行计划后同步 [plans/](plans/README.md) 状态。
- 达到退出标准才改 [product/roadmap.md](product/roadmap.md)；替代旧设计必须两端加替代关系。
- 事实优先链接而非复制；同一事实出现第二处时，改成指向主要维护位置。

目录规则与评测归属的调整记录见 [plans/2026-09-27-docs-four-directory-consolidation-results.md](plans/2026-09-27-docs-four-directory-consolidation-results.md)。
