# 文档整理记录（2026-09-27）

本文件是 [2026-09-27 文档组织与过时内容治理计划](./2026-09-27-documentation-reorganization.md) 的执行记录：检查基线、逐份文档清单、冲突矩阵、证据与验证结果。它不建立第二份产品状态表；阶段状态仍以 [版本路线](../product/versions/1.5.0/roadmap.md) 为准。

**范围：** 只动文档与为迁移必需的历史画布引用。未改应用代码、接口、数据库、测试、构建配置或依赖；未执行评测、未运行真实模型、未提交或推送。

---

## 1. 检查基线

执行前（2026-09-27，执行开始时）记录：

| 项 | 值 |
|---|---|
| 分支 | `feat/draft-in-cite-pane` |
| HEAD | `f54e7c84859307ef41ee3d42548a3521a5edbae5` |
| 已有改动 | `docs/references/思考.md`（已修改，未暂存） |
| 未跟踪文件 | `docs/references/亮点的地方.md`、`docs/roadmap/版本1.1代码解析.md`、`docs/plans/2026-09-27-documentation-reorganization.md` |
| `rg --files` 扫描范围 | `docs`（`src` / `tests` / `evals` 内无本轮相关命中；仓库内无 `AGENTS.md`） |

本轮受保护、不移动不覆盖不代提交的用户文件：

| 文件 | 状态 | 本轮处理 |
|---|---|---|
| `docs/references/思考.md` | 已修改（未跟踪前即有差异） | 未打开正文、未改动 |
| `docs/references/亮点的地方.md` | 未跟踪 | 未改动、未加入导航（未跟踪文件不入库，链接会指向不存在的内容） |
| `docs/roadmap/版本1.1代码解析.md` | 未跟踪 | 未改动；推荐归属见 §4 例外 E1 |

执行期间工作区状态若与上表不同，以执行时的实际基线为准。

---

## 2. 文档清单

状态取值：现行说明 / 有效未来设计 / 执行计划 / 历史记录 / 已被替代 / 待核实。另记实施阶段，避免把“设计已确认”写成“功能已完成”。

### 2.1 `docs/` 根与分类入口

| 路径 | 职责 | 状态 | 主要维护位置 | 依据 | 本轮动作 |
|---|---|---|---|---|---|
| `docs/README.md` | 文档总入口 | 现行说明 | 自身 | 各分类目录 | 重写为三条阅读路径 + 目录职责 + 冲突规则 |
| `docs/product/business-architecture.md` | 上层业务目标与边界 | 有效未来设计（含 V1 起点） | 自身 | 与 roadmap 一致 | 核查通过，不改 |
| `docs/roadmap/versions.md` | 阶段范围、退出标准、验收状态 | 现行说明 | 自身 | 证据见 §3.1 | 核查；V1.1 路径措辞记差异（C5），不改退出标准 |
| `docs/roadmap/版本1.1代码解析.md` | 代码讲解（用户未跟踪） | 历史记录 / 待核实 | 用户 | — | 保留原文件；列为例外 E1 |
| `CONTEXT.md` | 业务术语 | 现行说明 | 自身 | 与 product 无冲突 | 核查通过，不改 |
| `TODO.md` | 个人长期学习清单 | 历史记录（非契约） | 用户 | — | 在入口注明不是版本状态表 |
| `CLAUDE.md` | 给协作者的代码约束 | 现行说明 | 自身 | 与代码一致 | 核查通过，不改 |
| `README.md`（仓库根） | 项目首页 | 现行说明 | 自身 | 与架构/前端一致 | 只修与本次迁移相关的关联说明（§5.4） |

### 2.2 `docs/architecture/`（现行说明，逐份核查）

| 路径 | 状态 | 依据 | 本轮动作 |
|---|---|---|---|
| `architecture.md` | 现行说明 | 路由 `chat/router.py` L40/L46、`notes/router.py`、`notes/repository.py` `_normalize_note`、`alembic/versions/` head | 加核对日期与提交；其余不改 |
| `frontend.md` | 现行说明 | `home.html` 存在；`web/static/model-settings.js` 存在；`chat/router.py` 页面路由 | 加核对日期；不改布局描述 |
| `chat-tools.md` | 现行说明 | `chat/tools.py` 四工具 | 加核对日期 |
| `context-management.md` | 现行说明 | `chat/context_pack.py`、`context_compact.py` | 加核对日期 |
| `database.md` | 现行说明 | `db/models.py`；head `a9b4c2d1e8f0` | 加核对日期；与 plans/README 的旧 head 冲突（C2） |
| `retrieval.md` | 现行说明 | `retrieval/service.py`、`vector_store.py` | 加核对日期；修指向 `plans/draft-generation.md` 的历史链接（§5.3） |
| `observability.md` | 现行说明 | `observability/` | 加核对日期 |
| `rag-v1-retrospective.md` | 历史记录（复盘，非规格） | 与 RAG 报告数字一致 | 核查通过，不改 |
| `README.md`（本目录） | 现行说明（目录索引） | 各附件 | 修 canvas 行；分离历史区 |
| `DESIGN.md` | **已被替代**（屏幕/音频旧稿） | 仓库无 `capture/screen.py`、无 Whisper 主循环；两个画布无 `whisper/音频/截图` 命中 | 正文迁归档，原位留跳转页（§5.3） |
| `draft-generation.md` | **已被替代**（入库 Job 设想） | 现行对话→提案→人审→`notes/` 已在架构书 | 改为直达归档地址（避免多跳） |
| `noteagent-architecture.canvas.tsx` | **已被替代**（入库设想画布） | 仅 import `cursor/canvas`；`src/`/`tests/`/`evals/`/`scripts/`/配置零引用 | 迁 `docs/archive/designs/` |
| `noteagent-system-workflow.canvas.tsx` | **已被替代**（同上） | 同上；描述 Index Job + LangGraph 设想 | 迁 `docs/archive/designs/` |

### 2.3 `docs/plans/`（执行计划，逐份核定状态）

| 路径 | 计划声明的状态 | 勾选 | 本轮动作 |
|---|---|---|---|
| `README.md` | 索引 | — | 重排为执行中/已完成/历史参考；补漏项、修旧状态 |
| `2026-09-26-v1-acceptance.md` | 已交付（2026-09-26 回填，V1 验收通过） | 26/26 | 索引状态改为已完成 |
| `2026-09-26-chat-draft-in-citation-pane.md` | 已交付（2026-09-26 回填） | 31/31 | 索引补状态 |
| `2026-09-26-chat-layout-resize-and-draft-actions.md` | 已交付（2026-09-26 回填） | 23/23 | 索引补状态 |
| `2026-09-25-rag-quality-improvement.md` | 已交付（任务 1–4、6–9；任务 5 未做；8.4–8.6 按停止条件跳过） | 56/63 | 索引状态由“待执行”改为已完成（含跳过项） |
| `2026-09-25-model-switching-ui.md` | 已实现（§9 结果；423 passed, 1 failed） | 37/37 | 索引已有状态，核对 |
| `2026-09-25-model-switching-reliability.md` | 完成/部分（§9，2026-09-26：4 完成 1 部分） | 0/35（未勾，与结果矛盾） | **补入索引**；头部补执行状态与验证入口，正文保留原规格 |
| `2026-09-10-learning-note-quality.md` | 无整体状态标签；§ 记录了 2026-09-10 校准 | 无 | 索引补“部分完成/持续”说明 |
| `2026-09-10-chat-trace-tense.md` | 部分取代旧口径 | 无 | 索引标注 |
| `2026-09-09-chat-trace-cursor-flow.md` | 规格（未声明落地） | 无 | 索引按历史参考处理 |
| `2026-09-09-chat-trace-summary.md` | **已被取代**（被 cursor-flow） | 无 | 索引标注为历史参考 |
| `2026-09-09-chat-stream-trace.md` | 自称“原始规格” | 无 | 索引标注为历史参考 |
| `2026-09-09-cite-pane-isolation.md` | 无状态声明 | 无 | 已由后续计划覆盖，标注 |
| `2026-09-09-pending-draft.md` | 无状态声明 | 无 | 标注 |
| `2026-09-07-chat-citations.md` | 无状态声明 | 无 | 标注 |
| `2026-09-07-chat-cite-edit.md` | 无状态声明 | 无 | 标注 |
| `2026-09-06-prompt-eval.md` | 无状态声明 | 无 | 标注 |
| `2026-09-06-readme-homepage.md` | 无状态声明 | 无 | 标注 |
| `2026-09-06-readme-tutorials.md` | 无状态声明 | 无 | 标注 |
| `2026-09-08 之前`：`2026-09-05-documents-panel.md`、`2026-09-02-auto-index-on-approve.md` | 无状态声明 | 无 | 标注 |
| `2026-08-26-context-management.md` | 无整体状态；文内要求索引写“已实现，待审查” | 0/36 | 头部补执行状态；正文保留 |
| `2026-08-20-chat-history-persistence.md` | 无状态声明 | 0/23 | 同上 |
| `2026-08-20-conversation-rename-delete.md` | 无状态声明 | 0/8 | 同上 |
| `draft-generation.md` | **已被替代**（历史参考，2026-09-22） | 无 | 正文迁归档，原位留跳转页 |
| `2026-09-27-documentation-reorganization.md` | 本次计划 | 全部 | 收尾按实际完成度勾选 |
| `2026-09-27-documentation-audit.md` | 本记录 | — | 新建 |

“勾选为空”不等于未实现：`2026-08-20-*`、`2026-08-26-*`、`2026-09-25-model-switching-reliability.md` 的规格清单未回勾，但对应功能已实现并有测试或报告。本轮按“实现、测试存在与执行通过是不同证据”处理：只补执行状态与证据链接，不批量回勾未验证的条目。

### 2.4 `docs/evaluations/`

| 路径 | 状态 | 依据 | 本轮动作 |
|---|---|---|---|
| `README.md` | 现行说明 | 三本账划分 | 核查通过 |
| `note-quality.md` | 现行准则（v0.2） | — | 不改 |
| `rag-quality.md` | 现行准则（v1） | — | 不改 |
| `rag-v1-report.md` | 历史记录（已交付 2026-09-25） | `evals/rag/results/*/summary.json` + `var/evals/rag/*/config.json` | **勘误 §1.1**（§3.4） |
| `v1-acceptance-report.md` | 历史记录（已交付 2026-09-26） | `var/v1-acceptance/*`、`evals/prompt/results/` | 记录两处哈希口径（C7），不改成绩 |

### 2.5 `docs/design/`、`docs/decisions/`、`docs/references/`、`docs/tutorials/`

| 路径 | 状态 | 本轮动作 |
|---|---|---|
| `design/README.md` | 现行说明（目录职责） | 明确职责 + 不指向 `DESIGN.md` 旧稿 |
| `decisions/README.md` | 现行说明 | 保留；说明不强行为每个改动写 ADR |
| `references/README.md` | 现行说明（非契约） | 明确非契约；个人笔记不加入导航 |
| `references/secondbrainblog.md`、`references/参考.md` | 历史记录（摘录） | 不改 |
| `references/思考.md`、`references/亮点的地方.md` | 用户个人文件 | 不改（例外 E2） |
| `tutorials/README.md`、`tutorials/zh/*.md` | 现行说明 | 核查链接；不改步骤 |

无新内容的目录不补正文：`design/`、`decisions/` 保持空目录状态，只写明职责。

---

## 3. 冲突矩阵与证据

格式：声明 → 依据 → 判定 → 动作。

### 3.1 已确认并修正

**C1｜计划索引把已交付的计划写成“待执行”**

- 声明：`docs/plans/README.md` L11 记 `2026-09-26-v1-acceptance.md` 为“待执行”；L29 记 `2026-09-25-rag-quality-improvement.md` 为“待执行”。
- 依据：前者头部已有“执行结果摘要（2026-09-26 回填）”与“验收结论：V1 退出标准满足…tag `v1.0.0`”，勾选 26/26；后者有“逐项结果（2026-09-25）”，勾选 56/63，且 [rag-v1-report.md](../../evals/reports/rag-v1-report.md) 头部记“已交付（2026-09-25）”。
- 判定：索引状态过期。
- 动作：改为已完成，并写明 RAG 计划中任务 5 未做、8.4–8.6 按停止条件跳过——不能合并成“全部完成”。

**C2｜迁移 head 的两个值**

- 声明：`docs/plans/README.md` L14 要求生产库 `alembic upgrade head` 到 `3d1c2b8a9e4f`。
- 依据：`alembic/versions/` 链为 `f16dee6e3c97 → 3d1c2b8a9e4f → 8c2e1a4b7d90 → a9b4c2d1e8f0`；[database.md](../architecture/database.md) §1/§7 记现行 head `a9b4c2d1e8f0`（架构书 §5.7 同）。
- 判定：索引里的 id 是旧值；同一事实有两处维护。
- 动作：索引不再复制迁移号，改为链接 [database.md](../architecture/database.md)（事实优先链接）。

**C3｜`2026-09-25-model-switching-reliability.md` 未进索引**

- 声明：`docs/plans/README.md` 文件表未列该计划。
- 依据：文件存在（168 行），§9 记 2026-09-26 执行结果（4 项完成、1 项部分）。
- 判定：索引漏项。
- 动作：补入索引并标“已完成（1 项部分）”。

**C4｜RAG 报告 §1.1 的 dev 检索数字取错列**

- 声明：[rag-v1-report.md](../../evals/reports/rag-v1-report.md) §1.1 表中 `selected` 列为 `dev 9/18 = 50.0%`（Recall@5）与 `dev 8/18 = 44.4%`（Hit@3）。
- 依据：选定配置是 `intfloat/multilingual-e5-small` + 章节感知切块，`evals/rag/results/rag-v1-candidate-multi-dev/summary.json` 为 `full_recall_at_k 17/18 (0.9444)`、`hit_at_3 17/18 (0.9444)`；对应 `var/evals/rag/rag-v1-candidate-multi-dev/config.json` 记 `embedding_model=intfloat/multilingual-e5-small`、`embed_heading_prefix=true`。9/18 与 8/18 来自 `rag-v1-heading-prefix-dev`（仍是 MiniLM 的切块步骤）。holdout 列的 `11/12` 与 `rag-v1-selected-holdout/summary.json` 一致，正确。
- 判定：§1.1 把“切块步骤”的 dev 数字填进了“最终选定”列，属事实错误（同文 §1 摘要表与 §6.2 均为 17/18，自相矛盾）。
- 动作：§1.1 补勘误说明，dev 改为 17/18 = 94.4%（两项），保留运行身份与原表其余值。

**C5｜V1.1 路径措辞与实际支持边界**

- 声明：[versions.md](../product/versions/1.5.0/roadmap.md) §2.3 功能要求写“路径校验拒绝绝对路径、`..` 和嵌套目录”。
- 依据：`src/noteagent/notes/repository.py` `_normalize_note` 只接受 1–2 段（`Note.md` 或 `Folder/Note.md`），多于两段报 `nested paths are not allowed`；`_normalize_folder` 只接受单段。`tests/unit/test_note_repository.py` 有 `test_rejects_two_level_path`、`test_one_level_create_read_list`、`test_create_folder_rejects_nested`。[architecture.md](../architecture/architecture.md) §5.5 记为“拒绝空名、绝对路径、`..`、两层以上目录；允许 `Folder/Note.md`”。一层目录是 [2026-09-05-documents-panel.md](./2026-09-05-documents-panel.md) 的显式决定。
- 判定：准确边界是“**允许一层文件夹、拒绝两层及以上**”。路线图 V1.1 的“拒绝嵌套目录”是产品要求变更后未同步的表述，不是代码缺陷。
- 动作：**只记录差异**，不改退出标准；在 [versions.md](../product/versions/1.5.0/roadmap.md) §2.3 加一行边界说明指向 [retrieval.md](../architecture/retrieval.md)/架构书，是否改 V1.1 措辞留用户决定。

**C6｜前端“五个页面 / Vue”方向未进入任何现行说明**

- 声明（待否证）：本轮需确认现行说明没有被未来命名方向改写成多页面或 Vue。
- 依据：`src/noteagent/chat/router.py` 只有 `GET /`（L40）与 `GET /documents`（L46）两条页面路由，均下发同一模板；`src/noteagent/web/templates/home.html` 存在；`src/noteagent/web/static/model-settings.js` 存在。[frontend.md](../architecture/frontend.md) 明确“单页，无独立前端工程、无 Vue/React 打包”。
- 判定：现行说明与代码一致，未发现被未来方向污染。
- 动作：不改；[design/README.md](../product/README.md) 与 [docs/README.md](../README.md) 注明未来前端设计不在本轮范围、也尚未创建。

**C7｜同一份 v1-acceptance 报告里的两个 prompt 哈希**

- 声明：[v1-acceptance-report.md](../../evals/reports/v1-acceptance-report.md) §1 记“system prompt … SHA-256 `24d3623d…`”，§7 记“prompt SHA `25fbb8a9…`”，同一日期同一路径。
- 依据：`var/v1-acceptance/run-identity.txt` 记 `24d3623d… src/noteagent/chat/prompts/system.txt 8234 bytes`（`sha256sum`，原始字节）；各 run 归档副本 `evals/prompt/results/cases/v1-acceptance-regression_all_20260926-100340/system.txt` 与 `.../v1-acceptance-full_all_20260926-095957/system.txt` 原始字节同为 `24d3623d…`（8234 字节，含 64 处 CRLF）；而 `config.json` 的 `prompt_sha256 = 25fbb8a9…`，该值由 `src/noteagent/prompt_eval/run.py` L194-195 用 `prompt_path.read_text(encoding="utf-8")` 计算，即 **CRLF→LF 规范化后**的文本哈希。实测同一文件 `b.replace(b"\r\n", b"\n")` 得 `25fbb8a9…`，两值同源。
- 判定：不是两个 prompt，也不是两次配置；是“原始字节”与“通用换行解码后字节”两种口径。§7 比较两轮时两列同值，比较结论成立。
- 动作：在报告中加说明，写明两种口径各由谁产生；不据此推断配置差异。

**C8｜报告与报告的 L1/测试数字不互相覆盖**

- 声明：本轮是否应把会话中曾出现的 `490 passed` 改成报告里的 `478 passed`。
- 依据：`v1-acceptance-report.md` §3 记 `feat/v1-acceptance` / `c8161ab` 上 `pytest tests` 478 passed；`2026-09-26-chat-layout-resize-and-draft-actions.md` 记 490 passed（另一代码状态、另一日期）。
- 判定：不同提交、不同验证记录。
- 动作：不改任何一侧；在计划索引与报告中说明两者属于不同验证记录。

### 3.2 记录但不修（范围外或待用户决定）

| 编号 | 声明 | 依据 | 判定与处理 |
|---|---|---|---|
| D1 | RAG 报告 §10.5 与 §8 的“引用可定位到章节与原文 100%”门槛 | 报告 §1.1 实际 19/24 = 79.2% 未达 | 报告已如实记录为 ⚠️ 未达并要求用户定口径；不动门槛、不改结果 |
| D2 | 报告 §10.4 指“§3/§4 基线是切块改动前的配置，Agent 层需用新配置重跑” | 计划任务 9 的 holdout 复跑已完成（§4.1、§6） | 属报告内部时序，不在本轮范围 |
| D3 | `2026-09-25-rag-quality-improvement.md` 任务五（语料 v2）未做 | 计划自记“按用户选择未做”；报告 §10.8 同 | 保持未完成，不补做、不改语料 |
| D4 | Docker 镜像烘入 e5-small 未做构建验证 | RAG 报告 §6.3、复盘 §4.6 均已声明 | 保持“未验证”，本机无 Docker |
| D5 | `docs/roadmap/版本1.1代码解析.md` 的若干表述已过时（§2“镜像里通常已带 MiniLM”、§10“MiniLM embed”、§8“记笔记必须用原文标题”、§3“审批卡片”） | 现行配置是 `intfloat/multilingual-e5-small`（架构书 §6、README）；现行约定是材料标题树作为参考、不要求逐字相同（架构书 §5.3.3） | 用户未跟踪文件，本轮不改；列为例外 E1，推荐归属 `docs/tutorials/zh/code-walkthrough.md` |

---

## 4. 保留例外

| 编号 | 例外 | 原因 |
|---|---|---|
| E1 | `docs/roadmap/版本1.1代码解析.md` 未纳入正式导航 | 用户未跟踪文件；推荐归属 `docs/tutorials/zh/code-walkthrough.md`。本轮保留原文件，未纳入索引，内容未按现行代码修订 |
| E2 | `docs/references/思考.md`、`docs/references/亮点的地方.md` 未列入 `references/README.md` 的模块表 | 属用户个人笔记；未跟踪文件不加入导航（链接在干净克隆中不存在） |
| E3 | `docs/references/思考.md` 内指向 `../architecture/retrieval.md` 的链接 | 该目标未迁移；链接仍有效，未改动用户文件 |
| E4 | `docs/plans/` 中多份“无状态声明”的旧计划保留原文 | 不重写历史规格；只在索引给状态，避免把“规格存在”写成“功能已完成” |
| E5 | 两个画布迁到归档后仍 import `cursor/canvas` | 仅由 Cursor 画布宿主解析，仓库内无渲染器；迁移不改其引用 |
| E6 | 归档稿里的 `notes/*.md`、`context.md` 等为正文描述 | 不是文件路径解析；仅加历史状态说明，不做机械改写 |

---

## 5. 执行结果

### 5.1 新建

- `docs/plans/2026-09-27-documentation-audit.md`（本文件）
- `docs/archive/README.md`
- `docs/archive/designs/`（迁移目标目录）

### 5.2 迁移（原路径保留跳转页）

| 原路径 | 最终路径 | 原路径现状 |
|---|---|---|
| `docs/architecture/DESIGN.md` | `docs/archive/designs/screen-audio-early-design.md` | 跳转页 |
| `docs/plans/draft-generation.md` | `docs/archive/designs/ingestion-job-early-design.md` | 跳转页 |
| `docs/architecture/noteagent-architecture.canvas.tsx` | `docs/archive/designs/noteagent-architecture.canvas.tsx` | 已移走 |
| `docs/architecture/noteagent-system-workflow.canvas.tsx` | `docs/archive/designs/noteagent-system-workflow.canvas.tsx` | 已移走 |

`docs/architecture/draft-generation.md` 改为直接指向归档地址，避免多跳。

### 5.3 修订

| 文件 | 改了什么 | 依据 |
|---|---|---|
| `docs/README.md` | 重写为三条阅读路径 + 目录职责表 + 冲突判读规则 + 头部约定 | 任务 5 |
| `docs/architecture/README.md` | 头部加核对日期与提交；历史区改为指向 `docs/archive/` | 任务 4/5 |
| `docs/architecture/architecture.md` | 头部加核对日期、提交与“未运行测试”声明 | 任务 4 |
| `docs/architecture/retrieval.md` | 入库 Job 链接改指归档地址 | 任务 3 |
| `docs/architecture/DESIGN.md` | 正文迁归档，原位改跳转页 | 任务 3 |
| `docs/architecture/draft-generation.md` | 改为直达归档地址（去多跳） | 任务 3 |
| `docs/plans/draft-generation.md` | 正文迁归档，原位改跳转页 | 任务 3 |
| `docs/plans/README.md` | 重写：三档状态、补漏项、修旧状态、迁移号改为链接 | C1/C2/C3 |
| `docs/plans/2026-09-25-model-switching-reliability.md` | 头部补执行状态与验证入口（说明清单未回勾） | 任务 4 |
| `docs/plans/2026-08-26-context-management.md`、`2026-08-20-chat-history-persistence.md`、`2026-08-20-conversation-rename-delete.md` | 头部补“已实现，规格清单未回勾” | 任务 4 |
| `docs/evaluations/rag-v1-report.md` | §1.1 dev 检索数字勘误 + 勘误说明 | C4 |
| `docs/evaluations/v1-acceptance-report.md` | §1 补两个 prompt 哈希的同源说明 | C7 |
| `docs/roadmap/versions.md` | §2.3 补路径边界说明（差异记录，不改退出标准） | C5 |
| `docs/design/README.md` | 明确“有效未来设计”职责与归档入口 | 任务 5 |
| `docs/decisions/README.md` | 说明何时写 / 何时不写 ADR | 任务 5 |
| `docs/references/README.md` | 明确非契约、个人笔记不代改、未跟踪文件不入导航 | 任务 5 |
| `README.md`（仓库根） | 文档表：plans 行说明“待实现 ≠ 现状”，新增 archive 行 | 任务 4/5 |

未改写：`docs/product/business-architecture.md`、`CONTEXT.md`、`CLAUDE.md`、`docs/tutorials/**`、`docs/evaluations/{note-quality,rag-quality}.md`、`docs/architecture/{chat-tools,context-management,database,frontend,observability,rag-v1-retrospective}.md`（除头部约定与链接外未动）、`docs/plans/` 中其余历史计划正文、用户的三个文件。

### 5.4 验证结果

**命令与结果**（2026-09-27，工作区 `feat/draft-in-cite-pane`）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 旧路径全文搜索 | `grep -rn -E 'DESIGN\.md\|draft-generation\.md\|noteagent-architecture\.canvas\|noteagent-system-workflow\.canvas' docs README.md CONTEXT.md src tests evals` | 命中仅出现在：归档稿与其头部、归档索引、`docs/architecture/README.md` 历史区、`plans/README.md` 归档行、本整理记录、本次计划、以及两个跳转页本身。活动规格中无一处仍把旧稿当约束 |
| 失效假设搜索 | `grep -rn -E '一篇来源一篇\|成功后丢弃\|Collector 无写文件权限\|待执行\|Chat / Documents' docs` | 「一篇来源一篇 / 成功后丢弃 / Collector 无写文件权限」只出现在归档正文与归档说明中；「Chat / Documents」命中均为现行界面说明（保留）；「待执行」仅剩 `plans/README.md` 的分档标题与本次计划自身 |
| 相对链接 | 一次性只读脚本解析 `docs`、`src`、`tests`、`evals`、`notes`、`scripts`、`alembic`、根文档共 2176 个 Markdown 文件的 `[](...)` 与 `href="..."`，去掉 query/fragment、URL 解码后按所在目录解析 | 最后一次重跑：**1237 条相对链接，0 条断链**（含指向两个跳转页与新归档稿的入站链接） |
| 标题锚点 | 同上，对 20 条带 `#fragment` 的链接按 GitHub slug 规则比对目标文件标题 | **0 条不匹配**（含 `architecture.md#51/532/533/56/57/58`、`context-management.md#71`、`chat-tools.md#43`、根 README 同名锚点） |
| 画布完整性 | 与 `HEAD` blob 逐字节比对（按换行规范化） | 两个画布**内容零差异**，纯移动；仓库内无渲染器与代码引用，移动无运行时影响 |
| 空白符 | `git diff --check` | 唯一命中 `docs/references/思考.md:25` 行尾空格，属**用户原有改动**，本轮未触碰该文件；本轮新增/修改文件无新增空白问题 |
| 换行与编码 | 逐文件统计 CRLF 与孤立 LF | 本轮所有改动文件**无混合换行**；原有 LF 文件保持 LF，原有 CRLF 文件保持 CRLF；全部 UTF-8，无替换字符 |
| 改动范围 | `git status --short`、`git diff --stat` | 只涉及文档与仓库根 README；无 `src/`、`tests/`、`evals/`、`alembic/`、配置或依赖改动 |

**覆盖范围与限制：**

- 覆盖：`docs` 下整理前的 58 份文档与画布，加上本轮新增的归档稿、归档索引与本记录（整理后 `docs` 共 62 个文件，其中 60 份 Markdown）；另覆盖根 `README.md` / `CONTEXT.md` / `CLAUDE.md` / `TODO.md`、`src`/`tests`/`evals`/`notes`/`scripts`/`alembic` 下的 Markdown，以及 `var/` 内既有的验证快照副本。
- 未覆盖：外部 URL 未联网逐个访问；未运行测试、未跑评测、未启动服务、未做浏览器验收——本轮只做静态文档核对。除本记录列出的勘误外，没有其他数字被改动。
- 用于枚举链接的脚本为一次性只读脚本，落在 `var/`（运行时目录，不入库），验证后已删除，不扩展为产品工具链。

**仍需用户决策：**

1. RAG 报告 §1.1 更正后，「引用可定位到章节与原文 100%」门槛实际为 19/24 = 79.2%（D1）：是接受 `read_file` 整篇引用，还是要求引用一律来自检索片段。
2. [versions.md](../product/versions/1.5.0/roadmap.md) §2.3 的“拒绝嵌套目录”措辞是否随“允许一层目录”一并修订（C5）；本轮只记录差异。
3. 是否把 `docs/roadmap/版本1.1代码解析.md` 收进正式教程（推荐路径 `docs/tutorials/zh/code-walkthrough.md`）并按现行代码修订其中过时表述（E1/D5）。
4. 是否清理两个画布遗留的 `cursor/canvas` 宿主依赖（当前无需处理，仓库内无渲染器）。

### 5.5 边界声明

本轮未开展前端产品结构、Vue 迁移或页面设计：未创建 `design/` 下的任何方案、未新增前端里程碑、未修改路由与模板。`docs/design/` 保持为空目录，仅写明职责。相关设计留待后续独立任务。
