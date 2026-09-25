# 基础语料 v1 审查记录

冻结日期：2026-09-25。语料副本位于 `notes/`（被 `.gitignore` 排除，正文不进仓库），可由 `manifest.jsonl` 的 `sha256` 校验。

## 1. 盘点与排除

`notes/` 全量盘点（含被 Git 忽略的文件）共 20 个文件，排除 10 个：

| 排除文件 | 原因 |
|---|---|
| `README.md` | 数据目录说明，不参与索引 |
| `bak/2026-06-16.md`、`bak/context.md` | 备份与历史遗留 |
| `2026-06-21.md`、`2026-07-25.md`、`2026-07-27.md` | 按日期命名的会话/日记记录，非主题笔记 |
| `fa.md`（43 字符）、`Medical_AI_Papers.md`（26 字节） | 被截断的残稿，无可回答问题 |
| `Jinan_University_Degree_Certificate.md` | 个人事务文件 |
| `tutorial2.md` | 与 `Python_Tutorial_Intro` 同为官方教程第 1 章的整理版，同源重复 |

留下的 10 篇构成本语料。类别覆盖（允许重叠）：中文表达（`Software_Architecture_Design` 80% 中文、`Python_Tutorial_Intro` 63%、`Backtracking` 49%）、中英术语混合（`Writing_Effective_Tools_for_Agents`、`SQLAlchemy_psycopg`、`OWL2_Document_Overview`、`Agent_Design_Patterns`）、长文多章节（`OWL2_Document_Overview` 11526 字符、`Python_Tutorial_Overview` 9471 字符）、代码或表格（`Python_Tutorial_Overview` 42 个围栏、`OWL2_Document_Overview` 2 张表）、相近主题干扰（4 篇 Python 教程、`Backtracking` 与 `BinaryTree`）。

**语料拷贝是字节级的**：`sha256` 与原笔记逐一相等，原 `notes/` 零修改。

## 2. 来源与审查力度

| note_id | 来源 | 可做的审查 |
|---|---|---|
| `Python_Tutorial_Intro` | `sources/python_tutorial_ch1_whetting_your_appetite.md`（取自 `evals/prompt/learning_notes.jsonl` 的 l01，原文件 sha256 `be66e98e…`） | 可核对忠实与完整；但**不能证明**本笔记正是由该文本生成 |
| 其余 9 篇 | 无 | 只能判可读性与内部一致性；**不标记忠实性或完整性已验证** |

因此全部 10 篇的 `review_status` 均为 `provisional`，等人工确认后才有 `reviewed`。

## 3. 逐篇结论

十篇全部进入检索语料，无一被排除。缺陷按计划**记录而不修复**（v1 保留原文）。

### Python_Tutorial_Intro（1537 字符，10 个标题）

- **可回答**：为什么需要 Python（自动化文本处理、重命名照片、小型数据库、GUI、游戏）；shell 脚本/批处理的局限；Python 相对 C/C++/Java、Awk、Perl 的位置；标准模块范围（I/O、系统调用、socket、Tk）；解释型与交互式的收益；代码更短的三条原因；用 C 扩展的两种用途；命名由来与 Monty Python 无关；后续章节路线。
- **缺失上下文**：未说明哪些任务其实适合 shell 脚本（原文 `for some of these tasks` 的限定被压缩掉）；`Tk` 是什么、是否需额外安装；没有解释“非常高级的语言”；没有版本号或安装方式；标题不含章号，与第 2、3 章无法排序。
- **已发现缺陷**：与英文源文逐段比对**未发现无源可依的追加事实**，属忠实压缩改写。
- **分块相关**：无代码、无表格。

### Python_Tutorial_Interpreter（2643 字符，7 个标题）

- **可回答**：Unix 上解释器的安装路径与启动；退出方式与退出码；命令行编辑不可用的判断；`python -m module` 与 `python -c command` 的用法；`sys.argv[0]` 在无参数、`-`、`-c`/`-m` 下的取值；主提示符与欢迎信息；源码默认编码与可移植命名约定；shebang 行存在时编码声明写第二行。
- **缺失上下文**：提到的“Python 安装管理器”“交互模式”“codecs 列表”在本文件内无目标；示例混用 3.14 路径与 Python 2.x 脚注，未说明版本是否可替换。
- **已发现缺陷**（已核验）：
  - 脚注 `[1]` 的定义被排在末节 `2.2.1. 源文件的字符编码` 之下，与正文引用处（`2.1. 唤出解释器`）相距约 70 行 —— 按标题切块会把脚注并进“字符编码”。
  - 12 个代码围栏全部无语言标注（与 `Python_Tutorial_Overview` 的 ```python 标注不一致）。

### Python_Tutorial_Overview（9471 字符，7 个标题）

- **可回答**：`/` 与 `//`、`%` 的区别；交互模式 `_` 变量；`Decimal`/`Fraction`/复数；字符串引号转义与原始字符串；字符串不可变；列表赋值是引用而非复制；切片赋值可改变长度甚至清空；`while` 真值判定与 C 一致；`print(..., end=)`。
- **缺失上下文**：开头假定解释器已启动（启动方式在 `Python_Tutorial_Interpreter`，单独检索无法闭环）；脚注 `[1]`（`**` 与 `-` 优先级）与引用处相距约 440 行；“参见”段列出的文档名全无链接；未给出缩进宽度要求。
- **已发现缺陷**（已核验）：
  - **7 处围栏内注释形如 H1**，位于第 12、171、408、412、416、449、450 行（如 `# 这是第一条注释`、`# 斐波那契数列：`）。纯文本解析会把代码注释当成一级标题——这正是切块必须做围栏感知的直接证据。
  - `3.1.1` 把分组用圆括号写成 `(())`（空元组套括号），属录入错误。
  - `3.1.2` 的“参见”段残留 RST 转换痕迹（`文本序列类型 --- str`），且唯一保留英文原名 `Format string syntax`。
- **分块相关**：42 个代码围栏（41 个 ```python、1 个 ```text），无 Markdown 表格；`3.1.2` 内有一段 ASCII 画的索引位置图。

### Backtracking（2273 字符，25 个标题）

- **可回答**：回溯与递归的关系；剪枝不能改变穷举本质；五类问题；组合与排列的区别（“组合无序，排列有序”）；树的宽度/高度含义；三步模板与模板框架；`nonlocal` 何时必须写；LC93 的段合法性、参数设计、剪枝、易错点、测试用例。
- **缺失上下文**：全篇无完整可运行代码，模板框架是中文占位符伪代码；讲效率但不给复杂度；“`i+1` 或 `i`”没说何时用哪个；`nonlocal` 一节无代码示例；未标注剪枝应写在 for 的哪一步。
- **已发现缺陷**（已核验）：
  - **同一道 LC93 被两个同级 H2 重复覆盖**：`切割问题实战：复原IP地址（LC93）` 与 `切割问题实战：LeetCode 93 复原IP地址`，各带 5 个小节，约 70–80% 概念重叠；`- 结果用 ".".join(curpath) 拼接` 逐字出现两次。这不是补充说明，而是重复覆盖。
  - `startIndex` 与 `startindex` 大小写不一致；`times` 在两节被定义为“已分割段数”与“分割次数”，含义无法自洽。
- **分块相关**：1 个 ```python 围栏（模板框架），无表格。
- **评测含义**：LC93 相关查询会同时命中两节近义内容；命中判定按证据区间算，不受影响，但人工复核需知道两节互为重复。

### BinaryTree（601 字符，5 个标题）

- **可回答**：三种递归遍历顺序；递归三要素与栈溢出风险；迭代遍历为何用栈、前序入栈顺序；中序与后序迭代要点；层序遍历流程与常见应用；标记法核心；系统栈与显式栈的区别。
- **缺失上下文**：全篇无代码或伪代码；“标记法”没说弹出时如何区分标记与节点；无按层分组写法；无复杂度；无节点定义。
- **已发现缺陷**（已核验）：四个 H2 标题统一带 `[HH:MM:SS]` 时间戳前缀，属时间线记录残留，会污染 `heading_path` 的检索语义；末节是对迭代遍历要点的解释性重述。
- **分块相关**：语料中最薄一篇，无代码、无表格。作为“短笔记、可回答面窄”的样本保留。

### Agent_Design_Patterns（1287 字符，13 个标题）

- **可回答**：Workflow 与 Agent 的区分；增强型 LLM 的三项能力；五种工作流模式（提示链、路由、并行化、编排者-工人、评估-优化）各自的机制与适用场景；自主 Agent 的 ground truth 与检查点；核心三原则；ACI 的格式与措辞要求。
- **缺失上下文**：`ACI` 首次使用处未定义；`Sectioning`/`Voting` 未说结果如何聚合；路由未说谁做分类与失败兜底；评估-优化无迭代上限；只提 `MCP 协议` 名称；五种模式之间无选择标准；`SWE-bench` 无指标口径。
- **已发现缺陷**（已核验）：`各关注点分离处理，性能优于单次调用` 是无条件、无场景限定的性能断言，笔记内无依据。
- **分块相关**：无代码、无表格。

### Writing_Effective_Tools_for_Agents（7151 字符，16 个标题）

- **可回答**：工具作为“确定性系统与非确定性 agent 之间的契约”；原型→评估→协作的迭代流程；本地 MCP server / DXT 接入测试；评估任务为何不能太简单；从调用指标反推参数与描述问题；该实现哪些工具（`search_contacts` 而非 `list_contacts`）；命名空间两种命名法；为什么不要返回 UUID；token 效率与 Claude Code 的 25,000 token 上限；工具描述做提示工程的收益。
- **缺失上下文**：`tool evaluation cookbook`、`Developer Guide`、`tool annotations`、`interleaved thinking`、`rightsizing`、`held-out` 均无中文解释；`DXT` 只说缩写；示例 token 数（206 / 72）无出处。
- **已发现缺陷**（已核验）：正文引用脚注 `[1]`，全文没有对应定义（悬空引用）；H1 为文件名式英文而其余 15 个标题为“英文 + 全角括号中文”；同一对象在不同小节写作“工具描述 / spec / tool schema”。
- **分块相关**：2 个代码围栏（```bash、```text），都缩进在列表项内；无表格。

### Software_Architecture_Design（1518 字符，15 个标题）

- **可回答**：架构设计文档模版七节各写什么（文档简介、系统概述、组件/模块设计、技术方案、接口设计、性能优化、附录）；撰写说明五条（目的与读者、一致性、全面细致、重点突出、可读性）。
- **缺失上下文**：七节都只有一句话说明，无示例、字段清单或填写样例；无版本号/变更记录要求；“性能指标”无具体指标或测试方法；附录无格式要求；“读者群体”未说包含哪些角色。
- **已发现缺陷**（已核验）：
  - 撰写说明第 3 条与模版第 3 节近逐字重复（`使读者全面了解系统的设计方案和实现细节。` 一句完全相同）。
  - 模版正文夹带 `可以使用 Apifox 作为接口工具，它是功能强大的接口工具`，与“通用模版”定位不符且无依据。
  - 模版与撰写说明都从「1、」重新编号，引用“第 3 条”有歧义。
- **分块相关**：无代码、无表格。

### SQLAlchemy_psycopg（4741 字符，29 个标题）

- **可回答**：`psycopg[pool]` 独立安装；官方支持的 Python / PostgreSQL / PyPy 版本区间；`execute`/`fetchall` 等基本用法与单表达式快捷写法；`with` 退出时的提交/回滚语义与 psycopg2 的差异；表名列名用 `SQL + Identifier`；模板字符串查询（3.3 新增、PEP 750、Python 3.14 起）；格式说明符 `i`/`l`/`q`；`%s`/`%b`/`%t` 与二进制游标；失败后必须 `rollback()`；两阶段提交方法与 200 字符 ID 限制。
- **缺失上下文**：`PSYCOPG_IMPL` 的取值与读取时机；`InFailedSqlTransaction`、`UntranslatableCharacter` 只有英文类名；`Rollback(outer_tx)` 的 `outer_tx` 从何而来；`make_object/make_sequence` 无示例；Python 端如何构造 Multirange；只说可查看 `conn.info.encoding`，没说如何设置。
- **已发现缺陷**（已核验）：**6 个二级标题前缺空行**，紧贴上一节列表项（第 27、54、76、97、140、165 行）——严格 Markdown 解析器下标题可能不生效；`Psycopg`/`psycopg`/`PSYCOPG` 与 `PostgreSQL`/`PG` 混用；占位符与格式说明符规则在三节重复陈述。
- **分块相关**：**0 代码围栏、0 表格**，尽管内容几乎全是 API 用法。语料中唯一的“无代码 API 笔记”。

### OWL2_Document_Overview（11526 字符，16 个标题）

- **可回答**：OWL 2 本体的组成与存储形式；文档正式标题与版本（W3C Recommendation 2012-12-11）；functional-style syntax 与结构规范的关系；唯一必须支持的交换语法（RDF/XML）；Direct Semantics 与 SROIQ 的兼容；对应定理的结论；OWL 2 EL 的多项式时间与适用场景；OWL 2 RL 的 sound 但不 complete；与 OWL 1 的完全向后兼容；核心规范文档的数量与覆盖。
- **缺失上下文**：`图 1` 只有图题没有图，而第 2、3 节都以它作参照；`SROIQ`、`AC0`、`ground atomic`、`定理 PR1` 无中文解释与出处；`OWLED` 等致谢对象无参考文献条目。
- **已发现缺陷**（已核验）：`5.2` 声明自 Proposed Recommendation 以来无变化，`5.1` 却记录了自 Recommendation 以来关于 XSD 1.1 的实质变更，同一时间线互相矛盾；同一份规范有“Structural Specification 文档 / Structural Specification and Functional-Style Syntax / [OWL 2 Specification]”三种叫法；`OWL DL` 与 `OWL 2 DL` 混用。
- **分块相关**：语料中唯一含 Markdown 表格的笔记，共 2 张（`2.2 语法` 的 4 列语法对比表、`4 文档路线图` 的 13 行文档表）；无代码围栏。

## 4. 审查方式与核验

- 逐篇全文阅读后给出上表；**关键结论已用脚本对语料副本逐条核验**（15/15 通过），包括：Backtracking 的两节重复与逐字重复句、Overview 围栏内 7 处形如 H1 的注释行号、Interpreter 12 个无标注围栏与脚注位置、SQLAlchemy 6 处缺空行的行号、SAD 的近逐字重复、OWL2 的两张表头、BinaryTree 的 4 个时间戳标题。
- 审查由执行模型完成，因此：缺陷清单可信（有脚本复核），但**语义判断（如“这是一处无依据断言”）仍属自动审查**，需要人工确认，见 `docs/evaluations/rag-v1-report.md` 的集中清单。
- 本文件按计划**不修复任何缺陷**；修复只发生在后续的语料 v2（且不回写真实笔记）。

## 5. 复现方式

```powershell
# 盘点（含被 Git 忽略的文件）
rg --files --hidden --no-ignore notes
# 复核上面的缺陷结论与 10 条无答案标注，任一条不再成立就以非零码退出
uv run python scripts/verify_rag_corpus.py
# 从标注草稿重建查询集（逐字定位引文、推算 heading_path 与偏移，并跑正式校验）
uv run python scripts/build_rag_queries.py --corpus evals/rag/corpus/v1 `
  --draft evals/rag/queries.v1.draft.json --output evals/rag/queries.v1.jsonl
```

完整报告中的命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`。
