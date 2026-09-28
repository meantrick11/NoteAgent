# 四目录文档体系整理执行计划

> 执行者：Qoder。逐项执行并记录结果。本轮仅整理文档，不设计或实施前端，不修改应用代码，不安装依赖，不提交或推送 Git。

**状态：** 已执行（2026-09-27）。执行记录见 [2026-09-27-docs-four-directory-consolidation-results.md](./2026-09-27-docs-four-directory-consolidation-results.md)。

**日期：** 2026-09-27。

**目标：** 将正式文档收敛为 `architecture`、`product`、`plans`、`guides` 四个主要目录；评测标准和报告集中到根目录 `evals`；以现行架构为阅读主线，建立产品设计、执行计划、使用指南和评测证据之间的链接。

**需求依据：** 用户已确认：`product` 承载上层内容，包括产品要求、版本规划、设计和技术决策；`plans` 只承载每次 Agent 的执行计划与执行结果。`docs/references/` 是用户个人记录，整个目录不得更改。

**与前一轮的关系：** 前一轮 `2026-09-27-documentation-reorganization.md` 和 `2026-09-27-documentation-audit.md` 是已执行的治理记录，必须保留。本计划调整后续目录组织规则，不撤销已完成的事实核查和报告勘误，也不重写前一轮记录来假装当时采用了新结构。

**工具：** Markdown、PowerShell、Git 只读检查、`rg`、现有 Python。验证以文件基线、链接检查和文档一致性检查为主。

## 0. 不可突破的边界

1. **完整保护 `docs/references/**`：不得编辑、格式化、改编码、改名、移动、删除、新建目录内文件；包括 README、图片和附件。** 可以只读检查引用，但不要在报告里复制个人记录正文。任何执行前已有改动均保留，不用 Git 还原。
2. `notes/`、运行数据、密钥、模型配置、评测数据集和逐次运行产物不在修改范围。尤其不改 `evals/*/results/**`、语料、fixture、JSON/JSONL、prompt 副本及其配置。
3. 仅更新文档和迁移历史画布所必需的路径引用；不改变运行时代码、接口、测试、数据库、构建或依赖。若代码实际依赖将迁移的文档路径，保留兼容入口并记录，不顺手改代码。
4. 不新增 Home/Assistant/Library/Records/Settings 设计、Vue 选型或迁移方案、视频/会议方案。只定义未来这些文档的放置规则，本轮不写其正文。
5. 不改变版本范围、完成条件、业务边界或质量门槛。架构说明保持当前实际实现，不将未来设计写成已实现。
6. 不将技术决策的长期主要位置设为 `plans`。设计与决策在 `product`；计划引用已确认设计并拆解执行。现行架构可以概述已采用约束，并链接其决策依据。
7. 已有历史计划即使包含方案和理由，也不拆毁历史正文。本轮在入口说明历史格式与新约定的差异；只有仍然有效且需要长期维护的设计，才核实后提取到 `product`。
8. 不批量 `git add`、commit、push、reset、clean；不覆盖用户已有改动。目录合并基于当前工作区内容，不从 HEAD 还原后再迁移。
9. 编码先识别再读取，禁止以替换字符吞掉错误。只规范化本轮实际修订文件，不全仓库转码；`references` 一律逐字节不变。
10. 不为“只剩四个目录”强行删除兼容路径或个人文件。四个目录是正式文档主结构，`references` 是受保护的个人目录；必要旧路径是兼容例外，不是第二份权威正文。

## 1. 目标结构与权威内容位置

```text
docs/
├─ README.md
├─ architecture/
│  ├─ README.md                 # 架构目录索引
│  ├─ architecture.md           # 唯一系统架构总览，不复制到 README
│  ├─ frontend.md
│  ├─ database.md
│  ├─ retrieval.md
│  └─ ...                      # 已有现行专题
├─ product/
│  ├─ README.md                 # 上层文档索引、状态与职责
│  ├─ business-architecture.md # 保留现有产品/业务正文及名称
│  ├─ roadmap.md                # 从 roadmap/versions.md 迁入
│  └─ archive/                 # 原 archive 中失效设计，保留历史
├─ plans/
│  ├─ README.md                 # Agent 计划及执行记录索引
│  └─ YYYY-MM-DD-主题.md
├─ guides/
│  ├─ README.md
│  └─ zh/                      # 保留教程已有语言层级
└─ references/                 # 个人目录，完全不动

evals/
├─ README.md
├─ criteria/                   # 准则、指标、报告契约
├─ reports/                    # 汇总、复盘、阶段验收
├─ prompt/                     # 原有数据与运行产物，保持路径
├─ rag/
└─ agent/
```

未来有效设计和决策使用 `product/<主题>.md`，先不增加 `design/`、`decisions/` 子目录，也不新建空白方案。复杂到需要拆分时另行处理。

`architecture` 回答“现在是什么”；`product` 回答“要做什么、采用什么方案以及为什么”；`plans` 回答“Agent 本次如何执行、执行到了哪里”；`guides` 回答“如何使用、操作和开发”；`evals` 保存评测标准与证据。

## 任务 1：冻结执行基线与迁移清单

**新增：** `docs/plans/2026-09-27-docs-four-directory-consolidation-results.md`，只记录本次执行基线、迁移映射、验证结果和例外，不成为新的产品状态表。

- [x] 执行下列只读检查，将分支、完整 HEAD、工作区状态及本轮检查时间记入执行记录。

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --name-status
rg --files -g AGENTS.md -g '*.md' -g '*.mdx' -g '*.canvas.tsx' docs src tests scripts evals
```

- [x] 阅读适用的仓库指令；确认上轮治理改动仍可能全部未提交。本轮不得把这些改动当作可清理垃圾。
- [x] 对 `docs/references/` 递归保存“相对路径 → SHA-256”清单，含 README、隐藏文件及附件；清单放执行过程的临时目录，不放 references。遇到无法读取的文件先报告，不宣称已保护成功。
- [x] 对私人笔记以外的将迁移文档保存原始副本或哈希；对受保护的 `evals` 数据/结果目录保存路径与哈希基线，或使用现有可靠的内容比对方式。不要把敏感内容复制进交付文档。
- [x] 确认已知个人文件 `docs/roadmap/版本1.1代码解析.md` 当前为用户未跟踪内容：保留原位原文，不擅自移动到 guides。将其列为旧目录暂时保留的例外，后续用户另行处理。
- [x] 逐个枚举 `docs/evaluations/`，不要仅处理下表中的已知文件。所有实际文件都必须进入迁移清单或明确的保留例外。
- [x] 清单列：原路径、职责、目标路径、当前状态、入站引用、是否只读、兼容页策略。若目标路径已存在，先比较内容，禁止覆盖或静默选择一份。

**验收：** references 有完整基线，现有用户改动全部记录；迁移范围与例外明确；未开始前端设计。

## 任务 2：迁移上层文档、教程和失效设计

**迁移：**

| 原位置 | 目标位置 | 处理方式 |
|---|---|---|
| `docs/roadmap/versions.md` | `docs/product/roadmap.md` | 保留版本要求和原验收状态，只修路径与必要导航 |
| `docs/tutorials/README.md` | `docs/guides/README.md` | 合并为指南入口，保留语言层级 |
| `docs/tutorials/zh/*.md` | `docs/guides/zh/*.md` | 保留原文件名和使用步骤，核对所有同级资源 |
| `docs/archive/README.md` | `docs/product/archive/README.md` | 失效设计索引，不把其当有效要求 |
| `docs/archive/designs/*` | `docs/product/archive/designs/*` | 连同历史画布保留正文、失效原因、替代关系 |
| `docs/design/README.md` | 合并职责到 `docs/product/README.md` | 不生成未来设计占位正文 |
| `docs/decisions/README.md` | 合并职责到 `docs/product/README.md` | 决策属于上层，不放进 Agent 执行计划 |

- [x] 阅读 design/decisions 的当前全部内容。若执行时不再只有索引，逐份判断有效设计应迁入 product，失效设计迁入 product/archive，不丢失非空内容。
- [x] 搜索教程图片、附件、同级脚本与画布的引用，随文迁移仅文档资源；实际应用依赖则保留原路径并记录。
- [x] 每次移动前验证源、目标绝对路径在本仓库允许范围内，目标不存在。使用原生 PowerShell `Move-Item -LiteralPath`，禁止跨 shell 拼接、`-Force` 覆盖和未经核验的递归删除。
- [x] 移动后修正相对链接。旧稿仅更新位置与历史说明，不重新设计视频、会议或来源采集。
- [x] 上一轮原位置的兼容页如 `architecture/DESIGN.md`、`architecture/draft-generation.md`、`plans/draft-generation.md`，统一直达最终归档位置，不串联多级跳转。
- [x] 待任务 5 完成入站链接处理后，再处理旧目录；仅移除已核查的空目录或被替代的纯索引。保留个人文件及必要兼容页，不递归删除整个旧目录。

**验收：** 有效上层内容以 product 为主要入口；现行架构未被未来设计覆盖；个人文件未移动；历史正文保留。

## 任务 3：合并评测文档到 evals

**迁移：**

| 原位置 | 目标位置 |
|---|---|
| `docs/evaluations/note-quality.md` | `evals/criteria/note-quality.md` |
| `docs/evaluations/rag-quality.md` | `evals/criteria/rag-quality.md` |
| `docs/evaluations/note-quality.md` 以外其他质量准则 | 按原文件名迁到 `evals/criteria/` |
| `docs/evaluations/rag-v1-report.md` | `evals/reports/rag-v1-report.md` |
| `docs/evaluations/v1-acceptance-report.md` | `evals/reports/v1-acceptance-report.md` |
| `docs/architecture/rag-v1-retrospective.md` | `evals/reports/rag-v1-retrospective.md` |
| `docs/evaluations/README.md` | 内容合并到 `evals/README.md`，避免并存两份标准入口 |

- [x] 对其他发现的文件按实际职责判断：标准进 criteria，运行分析/验收/复盘进 reports；混合文件保留可追溯关系，不仅凭名字分类。
- [x] 保留报告原日期、提交、run ID、模型配置、分母、失败样例和上轮勘误；迁移不等于重新执行或重新验收。
- [x] 更新 `evals/README.md`：标准、汇总报告、三类评测数据与运行结果均在 evals 管理；删除“准则不在这里”“复盘不在这里”等失效导航文字。
- [x] 将旧 evaluations 索引中有效的运行和评分说明合并到 evals 入口或对应评测 README，不丢失三类评测各自计分、离线运行、数据隐私等边界；重复内容改链接。
- [x] 更新入口中的过时“当前”描述，例如旧索引的手动验收待执行、现行 prompt 仍为 v9。只依据可核实的报告/代码修订当前说明；属于某次历史运行的 v9 描述必须保留。
- [x] 不修改逐次 `results`、config、manifest、案例、prompt 或原始运行报告。若它们含旧文档链接，在旧目标保留跳转页解决，不批量改写历史产物。
- [x] criteria/reports 是否需要各自 README 根据入口可读性决定，不为新建目录而复制全文；可以直接在 evals/README 中列清索引。

**验收：** evals 成为评测唯一主要入口；原始数据和逐次运行产物逐字节不变；报告身份与历史成绩保持不变。

## 任务 4：建立以架构为中心的串联规则

**修改：** `docs/README.md`、`docs/architecture/README.md`、`docs/architecture/architecture.md`、相关架构专题；新增 `docs/product/README.md`；更新 `docs/plans/README.md`、`docs/guides/README.md`、`evals/README.md`。

- [x] docs 总入口突出“理解当前系统 → architecture/architecture.md”，同时提供产品规划、Agent 计划、操作指南、评测入口；references 只作为个人记录入口链接，不改其目录内任何内容。
- [x] architecture/README 只做索引，architecture.md 继续作为唯一系统总览，不生成第二份 overview 正文。
- [x] 架构总览串联：上层产品目标与路线图、现行子系统、操作指南、评测标准/验收证据。当前行为以代码核对；不在架构总览维护第二份版本进度表。
- [x] 在相关架构专题添加紧凑的“关联文档”：产品要求/设计依据、实施记录、验证依据、操作指南；后续演进有有效文档才加链接。只列实际相关项，不填空白栏目或虚构尚不存在的方案。
- [x] product 索引明确：产品与技术设计/决策均在这里；文档区分草案、已确认未实施、实施中、已实施、已替代。现行行为读 architecture，设计获批不代表完成。
- [x] plans 索引明确：每份计划引用产品设计或经确认的简单需求，列文件、步骤、验证、结果；一份上层设计可对应多份执行计划。执行遇到改变方案的需要，应先更新/确认 product 中的方案，再同步计划，不在计划内悄悄改变技术决策。
- [x] 历史计划保持正文，不将旧执行记录拆成假造的产品决策。必要时在索引注明“历史格式含设计说明，不作为当前设计主入口”。
- [x] 新计划的约定结构写在 plans/README：需求/设计依据、目标和范围、前置条件、执行步骤、验收检查、执行结果和遗留项；不要把“技术方案与关键决策”设为执行计划的权威章节。
- [x] 新 product 设计的约定结构写在 product/README：问题与目标、方案与理由、替代方案/代价、边界、验收要求、实施计划链接、落地后的架构链接。不实际创建任何前端专题设计。
- [x] plans 索引纳入本计划及执行记录，完成后回填实际状态。前一轮计划加“目录规则已由本轮调整”的导航说明即可，不能篡改其当时范围或执行结论。

**验收：** 从架构总览能找到产品依据、实际结构、相关计划、操作方法和验证证据；正文不重复维护；设计和执行职责明确。

## 任务 5：修复引用并保护只读区域

- [x] 枚举所有迁移路径的入站引用，覆盖根 README、CONTEXT、docs、src/tests/scripts 内 README 与文档、evals 的可编辑入口。兼顾 Markdown 内联/引用式链接、图片、HTML 链接、标题锚点和画布中的路径。
- [x] 可编辑文档中的普通导航链接改为最终路径。历史命令、运行记录、引用原话中的旧路径不做无差别替换；注明历史身份，或增加当前入口。
- [x] **references 中的任何链接都不改。** 如果链接目标被迁移，则在旧目标路径留下短兼容页，保留被引用的标题锚点或明确锚点，直接指向最终文档。兼容页写在 references 之外。
- [x] 同样处理受保护 evals 运行产物中的旧链接。若指向图片/画布等无法靠 Markdown 跳转保持原显示的资源，保留原资源路径作为只读兼容例外，不宣称资源已完全迁走。
- [x] 必要兼容页不保留第二份权威正文；每页明确“已迁移”和最终链接，不产生循环或多跳。
- [x] 删除旧 design/decisions 等入口前，确认有效内容已合并、没有受保护引用依赖；需要兼容的纯跳转保留。README 中说明四个主要目录之外的旧路径仅是兼容，不作为新内容放置位置。
- [x] 对个人 `docs/roadmap/版本1.1代码解析.md` 不编辑；如其中存在受迁移影响的旧链接，也用外部兼容入口保障，并记录保留旧目录的原因。

**验收：** 活动导航直达新路径，受保护文档不被修改且可继续访问迁移内容；所有保留旧路径有明确原因。

## 任务 6：验证、状态回填与交付

- [x] 再次对 references 枚举路径与 SHA-256，与执行前比较：必须零新增、零删除、零改名、零内容变更。该目录 Git 显示修改并不自动意味着本轮修改，以执行前后字节基线为准；不要回退原有变更。
- [x] 核对受保护评测数据和 results 基线；原始产物不变。检查迁移文件内容差异仅涉及已授权导航、状态修正、勘误保留和组织说明。
- [x] 校验全部新增/修改文档的本地链接及迁移文件的入站链接；按所在目录解析路径、处理中文/空格/URL 转义、检查标题 fragment；排除代码块里的示例路径。简单正则扫描只能辅助，不能宣称覆盖所有链接。
- [x] 检查 references 和历史产物中的旧链接是否能通过兼容路径访问。不联网逐个请求外部链接，报告外链未验证。
- [x] 使用下面的命令辅助检查；对关键词命中逐项分类，历史正文和兼容页可以保留旧路径，不能为清零搜索结果去改 references。

```powershell
rg -n --glob '*.md' --glob '*.mdx' 'docs/(design|decisions|roadmap|tutorials|evaluations|archive)|\.\./(design|decisions|roadmap|tutorials|evaluations|archive)/' docs README.md CONTEXT.md src tests scripts evals
rg -n --glob '*.md' '准则不在这里|复盘不在这里|技术决策|技术方案与关键决策' docs evals/README.md
git diff --check
git diff --stat
git diff --name-status
git status --short
```

- [x] 单独检查新建未跟踪文件，因为 git diff 不包含它们。将当前变更与执行前基线比较，区分上轮已有修改和本轮增量，不把整个工作区变化全部归给本轮。
- [x] 检查主要入口没有重复正文；product 持有上层设计和技术决策，plans 仅执行；architecture 不写未来能力为现状；references 完全未动。
- [x] 不运行应用全量测试或真实模型评测来为纯文档迁移背书；检查命令、核对范围、无法验证的项目如实写入执行记录。
- [x] 在执行记录中给出最终迁移映射、兼容页列表、保护基线比对结果、链接验证结果、遗留事项。若存在范围外问题，明确说明并保留，不静默扩大任务。
- [x] 回填本计划执行状态和勾选项，最终向用户报告四目录体系、evals 归属和主架构导航是否落实；不提交或推送。

## 最终验收清单

- [x] 正式文档以 architecture、product、plans、guides 四目录组织，references 作为个人目录保留且逐字节不变。
- [x] 产品目标、路线图、设计和技术决策以 product 为主要位置；没有新增独立 design/decisions 体系。
- [x] plans 的新约定只承载 Agent 执行计划与结果，引用上层设计；历史计划得到保留。
- [x] 评测标准、分析报告与复盘已集中到 evals；数据和原始运行产物没有改动。
- [x] architecture 是现行系统阅读主线，关联相关产品设计、执行计划、指南和评测证据。
- [x] 旧稿的历史属性与替代关系保留；兼容页、个人文件导致的旧目录保留有说明。
- [x] 本轮未新增前端设计、未实现 Vue 或五页面、未修改应用代码或依赖。
- [x] 交付最终执行记录和未解决事项；未进行 Git 提交或推送。
