# 四目录文档体系整理执行记录（2026-09-27）

本文件是 [2026-09-27 四目录文档体系整理计划](./2026-09-27-docs-four-directory-consolidation.md) 的执行记录：执行基线、迁移映射、保护基线比对、链接验证与例外。它不是产品状态表——阶段状态仍以 [product/roadmap.md](../product/roadmap.md) 为准。

**范围：** 只整理文档与必要的历史画布路径引用。未改运行时代码、接口、测试、数据库、构建或依赖；未安装依赖；未提交或推送。

---

## 1. 执行基线

| 项 | 值 |
|---|---|
| 检查时间 | 2026-09-27T15:57:10+08:00 |
| 分支 | `feat/draft-in-cite-pane` |
| HEAD | `f54e7c84859307ef41ee3d42548a3521a5edbae5` |
| 上轮治理改动 | **全部未提交**，按“已有改动”保留，未做任何还原 |
| 已知用户改动 | `docs/references/思考.md`（已修改）、`docs/references/README.md`（上轮改动）、`docs/references/亮点的地方.md`（未跟踪）、`docs/roadmap/版本1.1代码解析.md`（未跟踪） |
| 上轮新增（未跟踪） | `docs/archive/`、`docs/plans/2026-09-27-documentation-audit.md`、`docs/plans/2026-09-27-documentation-reorganization.md` |

### 1.1 保护基线（SHA-256）

逐文件 SHA-256 快照存放于执行临时目录 `var/docs-four-dir/baseline-hashes.json`（运行时目录，不入库；不含个人记录正文，只有路径与哈希）：

| 受保护范围 | 文件数 |
|---|---|
| `docs/references/**`（含 README、隐藏文件、附件） | 5 |
| `evals/prompt/**` | 154 |
| `evals/rag/**` | 43 |
| `evals/agent/**` | 14 |

`docs/references/` 文件清单：`README.md`、`secondbrainblog.md`、`参考.md`、`思考.md`、`亮点的地方.md`。全部可读，无读取失败项。本轮对该目录**零编辑**（比对结果见 §5.1）。

### 1.2 迁移清单

`docs/evaluations/` 已逐个枚举（5 个文件，全部进入迁移，无遗留例外）：

| 原路径 | 职责 | 目标路径 | 状态 | 只读 | 兼容策略 |
|---|---|---|---|---|---|
| `docs/evaluations/README.md` | 评测准则与账本划分入口 | 合并进 `evals/README.md` | 现行说明 | 否 | 旧路径不再保留（改由各文档直链 `evals/README.md`） |
| `docs/evaluations/note-quality.md` | 笔记正文质量准则 v0.2 | `evals/criteria/note-quality.md` | 现行准则 | 否 | 同上 |
| `docs/evaluations/rag-quality.md` | 检索准则 v1 | `evals/criteria/rag-quality.md` | 现行准则 | 否 | 同上 |
| `docs/evaluations/rag-v1-report.md` | RAG v1 实测报告 | `evals/reports/rag-v1-report.md` | 历史记录（含上轮勘误） | 否 | 同上 |
| `docs/evaluations/v1-acceptance-report.md` | V1 验收报告 | `evals/reports/v1-acceptance-report.md` | 历史记录 | 否 | 同上 |

其余迁移：

| 原路径 | 目标路径 | 状态 | 兼容策略 |
|---|---|---|---|
| `docs/roadmap/versions.md` | `docs/product/roadmap.md` | 现行说明 | 旧目录因用户未跟踪文件保留，无兼容页 |
| `docs/tutorials/README.md` | `docs/guides/README.md` | 现行说明 | 无 |
| `docs/tutorials/zh/{getting-started,local-dev}.md` | `docs/guides/zh/同名` | 现行说明 | 无 |
| `docs/archive/**`（5 个文件） | `docs/product/archive/**` | 历史记录 | 无 |
| `docs/design/README.md` | 职责合并进 `docs/product/README.md` | 现行说明（空目录） | 目录整体移除 |
| `docs/decisions/README.md` | 职责合并进 `docs/product/README.md` | 现行说明（空目录） | 目录整体移除 |
| `docs/architecture/rag-v1-retrospective.md` | `evals/reports/rag-v1-retrospective.md` | 历史记录（复盘） | 无 |

保留例外：

| 路径 | 原因 |
|---|---|
| `docs/roadmap/版本1.1代码解析.md` | 用户未跟踪的代码讲解；不编辑、不移动。因此 `docs/roadmap/` 目录保留，作为旧目录兼容例外 |
| `docs/architecture/{DESIGN,draft-generation}.md`、`docs/plans/draft-generation.md` | 上轮建立的兼容页，本轮改为直达最终归档位置 |
| `docs/references/**` | 受保护个人目录，逐字节不变 |
| `evals/*/results/**`、`evals/*/corpus/**`、案例与 config | 受保护运行产物，逐字节不变 |

检查结论：受保护的运行产物中**没有**指向迁移路径的链接（`evals/rag/results/*/config.json` 里的 `docs/...` 是运行当时 `git status` 的存档字符串，属历史证据，不改）。因此无需为它们建立兼容页。

---

## 2. 最终迁移映射与交付

### 2.1 迁移结果（全部用 PowerShell `Move-Item -LiteralPath`，移动前逐一验证源存在、目标不存在）

| 原路径 | 最终路径 |
|---|---|
| `docs/roadmap/versions.md` | `docs/product/roadmap.md` |
| `docs/tutorials/README.md` | `docs/guides/README.md`（重写为指南入口） |
| `docs/tutorials/zh/getting-started.md` | `docs/guides/zh/getting-started.md` |
| `docs/tutorials/zh/local-dev.md` | `docs/guides/zh/local-dev.md` |
| `docs/archive/README.md` | `docs/product/archive/README.md` |
| `docs/archive/designs/*`（4 个，含两个画布） | `docs/product/archive/designs/*` |
| `docs/evaluations/note-quality.md` | `evals/criteria/note-quality.md` |
| `docs/evaluations/rag-quality.md` | `evals/criteria/rag-quality.md` |
| `docs/evaluations/rag-v1-report.md` | `evals/reports/rag-v1-report.md` |
| `docs/evaluations/v1-acceptance-report.md` | `evals/reports/v1-acceptance-report.md` |
| `docs/architecture/rag-v1-retrospective.md` | `evals/reports/rag-v1-retrospective.md` |
| `docs/evaluations/README.md` | 内容合并进 `evals/README.md`，原文件删除 |

归档稿的正文、失效说明与替代关系全部随之保留；相对链接按新位置重算（含移动文件的“旧位置解析再重算”一次修正，共 26 处）。

### 2.2 新增

| 路径 | 内容 |
|---|---|
| `docs/product/README.md` | 产品目录索引：职责、状态口径（草案 / 已确认未实施 / 实施中 / 已实施 / 已替代）、设计与决策归属、新设计文档结构约定 |
| `docs/guides/README.md` | 指南入口（原 `tutorials/README.md` 重写，路径约定改为 `docs/guides/<lang>/`） |
| `docs/plans/2026-09-27-docs-four-directory-consolidation-results.md` | 本记录 |

### 2.3 重写与修订的入口

| 文件 | 改动 |
|---|---|
| `docs/README.md` | 以 architecture 为阅读主线重写；四个主要目录职责表；旧路径注明为兼容 |
| `docs/architecture/README.md` | 改为纯索引：不再有“复盘”单列，评测准则/报告集中在 evals；表格加“关联文档”列 |
| `docs/architecture/architecture.md` | 新增“关联文档”与 evals 索引；面板化改章节 6 的位置表；**修正“现行提示词是 v9”为 v11**（依据 `system.txt` 与 `iterations/` 逐字节比对） |
| `docs/architecture/{frontend,chat-tools,context-management,observability,retrieval}.md` | 各加一条紧凑“关联文档” |
| `docs/plans/README.md` | 明确只承载执行计划与结果；新增“新计划的约定结构”；纳入本计划与执行记录；前一轮计划标注目录规则已调整 |
| `evals/README.md` | 合并旧 evaluations 索引：criteria / reports / 三类数据 / 计分与边界 / 校准历史；删除“准则不在这里”“复盘不在这里” |
| 根 `README.md` | 文档表改为四目录 + evals 归属；项目结构树同步 |
| `src/**/README.md`、`tests/README.md`、`scripts/README.md` | 只改指向迁移路径的链接与标签 |
| `src/noteagent/chat/prompts/README.md`、`.../iterations/README.md` | 现行版本由 v10 更正为 v11，补 v11 归档行（依据逐字节比对） |

### 2.4 兼容与保留路径

| 路径 | 保留原因 | 处理 |
|---|---|---|
| `docs/architecture/DESIGN.md` | 上轮兼容页 | 改为直达 `docs/product/archive/designs/screen-audio-early-design.md` |
| `docs/architecture/draft-generation.md` | 上轮兼容页 | 改为直达归档的入库 Job 设想 |
| `docs/plans/draft-generation.md` | 上轮兼容页 | 同上，另注明屏幕采集旧稿位置 |
| `docs/roadmap/`（仅 `版本1.1代码解析.md`） | **用户未跟踪文件**，不编辑不移动 | 目录保留；入口已注明是兼容例外；该文件内的旧路径是反引号文字，不构成断链 |
| `docs/references/**` | 受保护个人目录 | **逐字节不变**；其链接目标（`../architecture/*`）未迁移，无需兼容页 |

删除的旧目录：`docs/design/`、`docs/decisions/`（纯索引，职责已并入 `product/README.md`）、`docs/evaluations/`（内容已迁/已合并）、`docs/archive/`、`docs/tutorials/`（已清空）。删除前逐一确认目录为空。

---

## 3. 导航与约定（落实检查）

| 要求 | 落实位置 |
|---|---|
| docs 总入口突出“现行系统 → architecture/architecture.md” | `docs/README.md` 首段 + 三条阅读路径 |
| architecture/README 只做索引，architecture.md 是唯一总览 | `docs/architecture/README.md` 首段明写，未新增第二份总览 |
| 架构与产品/计划/指南/评测互链 | `architecture.md` 新增“关联文档”；五个专题各一条“关联文档” |
| product 持有设计/决策与状态口径 | `docs/product/README.md` |
| plans 只承载执行计划，引用上层设计 | `docs/plans/README.md` 首段与“新计划的约定结构” |
| 历史计划保持正文 | 未拆改正文；只在计划索引与前一轮计划顶部加导航说明 |
| 评测唯一入口在 evals | `evals/README.md`；架构书与各目录 README 均指向它 |

---

## 4. 验证

### 4.1 保护基线比对（SHA-256，执行前快照 `var/docs-four-dir/baseline-hashes.json`）

| 范围 | 文件数 | 结果 |
|---|---|---|
| `docs/references/**` | 5 | **零新增、零删除、零改名、零内容变更** |
| `evals/prompt/**` | 154 | 逐次运行产物全部不变；仅可编辑入口 `prompt/README.md` 改了链接 |
| `evals/rag/**` | 43 | 同上；仅 `rag/README.md` 改了链接 |
| `evals/agent/**` | 14 | 同上；仅 `agent/README.md` 改了链接 |

受保护的 `results/`、`corpus/`、`config.json`、manifest、案例 JSONL 与 prompt 副本**未做任何改动**（上述三个 README 之外的哈希全部一致）。上轮对 `docs/references/README.md` 的改动属执行前已有状态，已保留且未再改。

受保护产物内部的 Markdown 链接经扫描：**0 条断链**，无需为其建立兼容页。`evals/rag/corpus/v1/audit.md` 里以反引号形式提到 `docs/evaluations/rag-v1-report.md`，属历史正文中的文字引用而非链接，保留为只读例外。

### 4.2 链接与锚点

| 检查 | 结果 |
|---|---|
| 本地相对链接（`docs`、`src`、`tests`、`scripts`、`evals`、`notes`、根文档；跳过 `references/` 与受保护产物） | **753 条，0 条断链** |
| 带 fragment 的链接按 GitHub slug 比对目标标题 | **0 条不匹配** |
| 覆盖形式 | 内联链接、图片语法、HTML `href`、代码块外的路径；代码块内容已剔除，避免误判 |

### 4.3 检索命中判读

| 检查 | 命中与判读 |
|---|---|
| `docs/(design\|decisions\|roadmap\|tutorials\|evaluations\|archive)` 等旧路径 | 仅两类命中：`docs/product/README.md` 中解释“不另开 design/decisions 子目录”的说明文字；`evals/rag/corpus/v1/audit.md` 受保护正文。**无活动导航指向旧路径** |
| `准则不在这里` / `复盘不在这里` | 旧入口已删除；仅剩本计划（作为待办描述）与 `plans/README.md`（新约定表述） |
| `技术方案与关键决策` | 仅出现在约定说明中（明确“不要设为执行计划的权威章节”），不是章节标题 |
| `git diff --check` | 0 问题（`docs/references/思考.md` 的行尾空格属用户原有改动，本轮未触碰） |
| 改动范围 | `docs/**`、`evals/**` 的文档、`src|tests|scripts` 的 README、根 `README.md`；**无应用代码、接口、测试、数据库、构建或依赖改动** |
| 换行与编码 | 本轮所有改动文件无混合换行；既有 LF/CRLF 各自保持；UTF-8 无替换字符 |

### 4.4 未验证项目

- 未运行应用全量测试、未跑评测、未启动服务：本轮为纯文档迁移，结论不依赖运行结果。
- 未联网逐个访问外部 URL；文中外链未验证。
- 未做 Git 提交或推送。
- 未验证“干净克隆”下的链接（未跟踪文件 `docs/roadmap/版本1.1代码解析.md`、`docs/references/亮点的地方.md` 不会出现在他人克隆中；本轮未把它们加入任何导航，正是为此）。

---

## 5. 遗留事项

1. `docs/roadmap/` 目录仅因用户未跟踪的 `版本1.1代码解析.md` 保留。若该文件收进 `docs/guides/zh/code-walkthrough.md` 并按 v11 代码修订，`docs/roadmap/` 即可移除。
2. 三个旧兼容页（`architecture/DESIGN.md`、`architecture/draft-generation.md`、`plans/draft-generation.md`）在确认没有外部依赖后可删；当前保留为直达归档的跳转。
3. 历史计划正文仍含旧路径文字（如 `docs/evaluations/`、`docs/tutorials/`），按计划未做无差别替换；如需统一，属另一次编辑任务。
4. 上轮记录中的两项待决策（RAG 引用到章节级的口径、路线图 V1.1 路径措辞）仍未处理，未因本次整理而改变。
5. 本轮未创建任何前端设计：`docs/product/` 下只有 README 的结构约定，没有 Home/Assistant/Library/Records/Settings 或 Vue 相关内容。
