# NoteAgent RAG 基础语料、评价标准与逐步优化执行计划

> 执行对象：Claude Code。按任务顺序执行并勾选检查项；每阶段留下可复查的产物和报告。如果执行环境具有 executing-plans 技能，可用它逐任务推进；本计划本身包含执行所需的范围、接口、指标和交付要求。

**Goal:** 先建立可复用的基础笔记和固定任务集，再用指标定位并改善笔记、切块、向量表示、检索和 Agent 使用效果。

**Architecture:** RAG 保持为 Agent 按需调用的历史笔记检索工具，支持回忆旧知识以及将新内容匹配到旧笔记。检索返回证据和位置，Agent 继续推理；修改旧笔记前阅读目标全文，生成草稿后沿用用户审批。评测分为直接检索和真实 Agent 两层，共享冻结的语料与证据标注。

**Tech Stack:** Python 3.13+、现有 LangChain 文本切分器、sentence-transformers、Chroma、pytest、JSONL 和 Markdown；Agent 层复用现有 ChatAgent 和工具。

**Spec:** 本文即本次执行规格；同时阅读 `CLAUDE.md`、`docs/architecture/retrieval.md`、`docs/architecture/chat-tools.md`、`docs/evaluations/note-quality.md`、`docs/roadmap/versions.md`。本计划收敛于用户确认的检索工具定位，不扩展为通用 RAG 平台。

## 执行前已确认的决策（2026-09-25）

执行前已与用户逐项确认；与本文正文冲突时以本节为准。偏离正文的地方在下方标注。

| # | 决策 | 内容 |
|---|---|---|
| 1 | 提交范围（**偏离**） | 语料正文、`queries.v1.jsonl`、`rag_cases.v1.jsonl` 留在本地并加入 `.gitignore`；仓库只提交 `manifest.jsonl`（含 sha256）、`audit.md` 摘要、各 run 的 `summary.md`、代码、测试与文档 |
| 2 | 语料组成 | 计划中的 10 篇原样使用；「中文」按「中文表达的笔记」理解，不另凑纯中文样本 |
| 3 | 暂停点 | 批次 1（任务 1–4）后暂停一次，由用户决定任务 5–8 的范围；批次 2 内自主推进；任务 9 前再暂停 |
| 4 | 向量候选 | bge-small-zh-v1.5 + paraphrase-multilingual-MiniLM-L12-v2；**任何下载先问用户**；权重落 `D:\develop\aidevelop\transformer_models`；任务 7 允许跳过 |
| 5 | 达标后的范围 | 任务 6 必做（引用可追溯率 100% 与 heading_path 依赖它）；任务 7 在基线已达标时跳过并在报告写明 |
| 6 | 报告位置（**偏离**） | 含全部命中正文的完整报告落 `var/evals/rag/<run-id>/`（`var/*` 已忽略，不提交）；仓库只留 `evals/rag/results/<run-id>/summary.md`。原文要求报告放 `evals/rag/results/` 并记录全部命中内容 |
| 7 | 标注复核 | 只提交「无答案 + 冲突/重复」约 20 条集中清单；quote 与偏移由代码逐条校验，用户抽查 5 条格式 |
| 8 | 真实调用 | 授权使用 `.env` 现有 DEEPSEEK_API_KEY + deepseek-v4-flash；**先只跑 dev 12×3=36 轮**；会话存储用 `sqlite:///:memory:`（同 `prompt_eval`），不连接 PostgreSQL，因此不需要评测 DSN，不构成 blocked |
| 9 | Agent 层评分 | 确定性判定：`[[cite:N]]` → `CitationRegistry` → 注册的 quote/chunk 是否覆盖必需证据单元；不使用 LLM Judge |
| 10 | 生产索引 | 只改代码默认值并加「配置与已有 collection 不匹配即报错要求重建」的检测；不碰 `chromadb_persist`；重建/回退方案交付后由用户决定何时执行 |
| 11 | 分支与提交 | 新建 `feat/rag-quality-v1`，本地提交三批、不 push、Conventional Commits；原分支 `codex/business-architecture` 上的未提交文档改动保持不动 |
| 12 | v2 修订范围 | 只改语料副本 `evals/rag/corpus/v2/`；真实 `notes/*.md` 一律不动，回写建议交用户决定 |
| 13 | 批次 2 改动上限 | `retrieval/service.py`、`chat/tools.py`、`chat/citations.py`、`chat/prompts/system.txt` 四处都可改，每项独立提交、独立前后对照、重跑 dev；不改「提案 → 人审 → 写盘」这条边界 |

**执行前已声明的风险：**

1. MiniLM 接近英文单语模型，中文查询基线召回可能显著低于门槛。这属于计划预期的「先记录当前结果」，主要收益预期来自任务 7；不得用调参掩盖基线事实。
2. 现行检索无相似度阈值，无答案查询在检索层仍会返回 3 条。「历史无答案正确处理率」只能在 Agent 层评价，基线可能很低。
3. dev 24 / holdout 16 样本量小，单条查询约等于 4–6 个百分点。报告必须同时给出成功数/总数，不以百分比掩盖噪声。
4. 证据单元必须短于切块长度（当前 500 字符），否则单块无法完整覆盖，Recall 会被切块边界而非检索质量拖低。标注阶段先剔除跨块证据单元或另立替代位置。

## 0. 执行约束与当前证据

- 首先检查工作区状态，保留已有未提交修改；仅提交本任务文件，遵循仓库提交约定。
- 正式 Markdown 仍是事实源。评测不得写入真实 `notes/`、生产 Chroma 或正常聊天数据库。
- 本次不增加网页搜索、请求分流、独立检索服务、GraphRAG 或多 Agent 编排，不以换向量数据库作为预设目标。
- 先记录当前结果再优化。模型或数据缺失属于未完成，不得用假向量结果冒充真实检索质量。
- 任务 1–5 是必做基础；任务 6–8 按诊断逐项执行，达到指标即可停止增加复杂度；任务 9 完成验收和交接。
- 候选模型下载和外部模型调用按环境授权执行。无法访问时继续完成离线部分，报告准确的受阻命令和原因，不声称整体通过。
- 文件路径均相对仓库根目录。本文列出的新脚本和命令是待实现接口，目前尚不存在。

截至本计划编写时已核对：

| 部分 | 当前实现与可复用资源 |
|---|---|
| 笔记 | `notes/` 有未被 `rg --files` 默认列出的本地笔记，盘点必须覆盖被 Git 忽略的数据文件 |
| 切块 | `retrieval/chunker.py` 使用 RecursiveCharacterTextSplitter，500 字符、50 重叠 |
| 向量 | `retrieval/embedder.py` 统一调用 encode；Settings 默认 all-MiniLM-L6-v2，运行配置可能覆盖 |
| 存储 | `retrieval/vector_store.py` 使用 Chroma PersistentClient |
| 检索 | `RetrievalService.search(query, top_k=3)`；聊天工具显式传入 top_k=3 |
| 工具结果 | 当前 fragments 提供 content 和条件性 source_id，尚未直接提供 file_name、heading_path |
| 评测 | `evals/rag/` 只有 README；现有 prompt_eval 的 _FakeRetrieval 不能证明真实召回效果 |
| 笔记标准 | `docs/evaluations/note-quality.md` 已定义任务匹配、忠实、完整等标准，应复用 |

## 1. 任务一：盘点并建立独立基础笔记集

**新增：** `evals/rag/corpus/v1/notes/`、`evals/rag/corpus/v1/sources/`、`evals/rag/corpus/v1/manifest.jsonl`、`evals/rag/corpus/v1/audit.md`。

- [x] 用 `Get-ChildItem notes -Recurse -File` 或 `rg --files --hidden --no-ignore notes` 盘点本地笔记，排除 README、备份、会话记忆和明显个人事务文件。
- [x] 全文阅读候选后选取 10 篇。优先候选：Python_Tutorial_Intro、Python_Tutorial_Interpreter、Python_Tutorial_Overview、Backtracking、BinaryTree、Agent_Design_Patterns、Writing_Effective_Tools_for_Agents、Software_Architecture_Design、SQLAlchemy_psycopg、OWL2_Document_Overview。
- [x] 不按文件名认定质量。若候选空白、损坏或高度重复，使用 `evals/prompt/fixtures/learning_notes/good.md` 及 `learning_notes.jsonl` 内原始材料建立替代笔记；仍不足时补写少量明确标记为 synthetic 的自包含材料，不假称用户真实笔记。
- [x] 复制到独立目录。基线保留原文，不先为检索结果改写笔记；不强制把所有笔记变成统一模板。
- [x] 可获得的原始材料单独保存至 sources。复用 learning_notes.jsonl 时提取实际来源正文，保留原 case id 和原文件哈希。
- [x] 每篇建立 manifest：note_id、相对 file、sha256、origin_path、source_file（可空）、source_status、review_status、issues。
- [x] source_status 取 available / missing / synthetic；review_status 取 reviewed / provisional。没有来源时只能判断可读性和内部一致性，不标记忠实性、完整性已验证。
- [x] corpus 至少覆盖中文、中英术语混合、长文多章节、代码或表格、相近主题干扰；这些类别允许重叠。不能通过复制同一篇多个版本凑 10 篇。
- [x] audit.md 逐篇记录可回答的问题、缺失上下文、已发现错误，以及是否进入检索语料。明显错误先排除或修正并保留差异，不能放入受信答案。

**质量约定：** 基础集是冻结的可检查样本，不是唯一标准写法。已有 good / literal / omitted / hallucinated 继续作为笔记质量正反例；负例不混入可信检索语料，另用于验证“答案根本没保存下来”的诊断。

**完成条件：** 10 篇语料可追溯、逐篇有审查记录、原笔记零修改。自动生成的审查先标记 provisional，并提供集中人工抽查清单；可以继续工程实验，但未完成的人工确认必须进入报告。

## 2. 任务二：建立证据标注和最小 RAG 标准

**新增：** `docs/evaluations/rag-quality.md`、`evals/rag/queries.v1.jsonl`、`evals/agent/rag_cases.v1.jsonl`。

- [x] 先依据笔记正文列出可核对的知识点，再编写自然提问；问题避免逐字复制答案，覆盖口语、省略主题的多轮表达和相近概念。
- [x] 建立 40 条直接检索查询：30 条有答案、10 条无答案。有答案项分为直接事实 8、同义改写 8、中英术语 6、跨段或易混淆问题 8。
- [x] 在第一次实验前固定 dev 24 条、holdout 16 条；dev 含 18 条有答案和 6 条无答案，holdout 含 12 条有答案和 4 条无答案。相同信息需求的改写使用同一个 group_id，整个 group 只进入一种 split。
- [x] 无答案样例必须核查整个语料，其中至少一半包含与已有内容相近的术语；允许召回相关背景，但不能把它判为回答证据。
- [x] 用原文证据而非 chunk_index 标注，避免切块变化后标准失效。证据写 note_id、heading_path、start_char、end_char、quote；偏移基于 UTF-8 解码文本的 Python 字符下标，范围为左闭右开。
- [x] 同一个问题可有多个必需 evidence unit；同一个 unit 可有多个可替代证据位置。每个 unit 写明必须保留的事实或条件。
- [x] 建立 20 条 Agent 场景：历史知识回答 6、新内容匹配并补充旧笔记 6、历史无答案 4、无需检索的普通对话 4。其中 dev 12 条按 4/4/2/2 分配，holdout 8 条按 2/2/2/2 分配；按信息需求分组隔离。
- [x] 补充场景提供明确 new_content、目标笔记、期望 action、必须保留的原有事实；至少 2 条包含重复信息、2 条含需要澄清的冲突，不能只测试正常追加。
- [x] 调试期间只用 dev。holdout 在选定候选后使用；一旦据其失败案例修改方案，就将其视为已见数据，追加新的未见验收样本，不反复宣称同一集合是盲测。

单条查询使用以下字段契约；dataset.py 实现相应读取和运行时校验。实际内容与偏移从冻结语料提取，不填写虚构位置：

```python
from typing import Literal, TypedDict

class EvidenceLocation(TypedDict):
    note_id: str
    heading_path: str
    start_char: int
    end_char: int
    quote: str

class EvidenceUnit(TypedDict):
    id: str
    fact: str
    alternatives: list[EvidenceLocation]

class QueryCase(TypedDict):
    id: str
    group_id: str
    split: Literal["dev", "holdout"]
    query: str
    category: Literal["fact", "paraphrase", "mixed_language", "multi_evidence", "unanswerable"]
    answerable: bool
    evidence_units: list[EvidenceUnit]
```

正式数据校验必须拒绝空 evidence、start_char >= end_char、quote 与正文切片不一致、缺失 note_id、无答案却标正证据、同组跨 split 等情况。参考答案可写为事实要点，不要求固定措辞。

**初始验收指标（项目暂定门槛，不代表行业标准）：**

| 指标 | 计算方法 | 门槛/用途 |
|---|---|---|
| Evidence Recall@5 | 每条有答案查询：前 5 个片段覆盖的必需 unit 数 / 全部必需 unit 数，再对查询平均 | >= 85%；对应现有路线图 Recall@5，明确细化到证据单位 |
| Evidence Hit@3 | 前 3 个片段至少覆盖一个完整 unit 的有答案查询比例 | >= 80%；对应当前工具返回 3 条的实际表现 |
| MRR@5 | 第一个覆盖完整 unit 的片段排名倒数，未命中记 0，再取平均 | 诊断排序，暂不设硬门槛 |
| 引用可追溯率 | 实际返回引用中可定位到当前文件、章节和原文的比例 | 100%；无引用时记 N/A，不能自动满分 |
| 历史任务检索调用率 | 明确依赖历史知识的任务中确实调用检索的比例 | >= 90% |
| 无需检索误调用率 | 普通对话中不必要调用检索的比例 | <= 10% |
| Agent 任务成功率 | 回答事实正确且有依据，或补充目标/action/内容正确且未破坏原有信息的完整任务比例 | >= 85%，按场景分别报告 |
| 历史无答案正确处理率 | 清楚说明未找到历史依据、未把背景片段冒充答案的比例 | >= 90%；允许明确区分的一般知识说明 |
| 写入与更新安全 | 未审批不写正式笔记，拒绝不改索引，替换/删除后无旧证据 | 所有确定性用例通过 |
| 性能 | 热查询 p50/p95、冷启动、建索引耗时、进程内存、工具返回 token 数 | 先测基线；无预先说明的取舍，热查询 p95 不超过基线 2 倍 |

unit 命中规则：同一文档中，返回片段的原文区间覆盖一个 alternative 的完整证据区间才计覆盖；同一文档的多个命中区间可以合并后判断，但只有真正交给消费者的内容才算。Hit 和 MRR 要求单个片段覆盖至少一个 unit。按 unit 去重，不因重叠块重复加分。文件命中率另作诊断，不替代证据命中率。

小样本报告必须同时给出成功数/总数和百分比，逐场景展示；4 个无答案样例的 90% 门槛实际要求 4/4。LLM 评分不能替代证据核查；同模型自评要明确标记，不当作独立质量认证。

质量门槛分别应用于 dev 与 holdout，不允许合并后掩盖 holdout 失败。Agent 调用率分母包含历史问答、历史补充和历史无答案场景；每次真实运行算一次机会，另报按 case 汇总的三次成功分布。普通对话不计入历史任务成功率，以免容易样例抬高结果。相同 corpus/query split 下才比较新旧延迟。

## 3. 任务三：实现可重复的直接检索评测

**新增：** `src/noteagent/rag_eval/{__init__,dataset,metrics,run}.py`、`scripts/eval_rag.py`、`tests/unit/test_rag_eval.py`。
**复用：** `retrieval/service.py`、`embedder.py`、`vector_store.py`、`models.py`。

接口责任：dataset 读取并校验语料/查询；metrics 只计算分数；run 构建隔离索引、运行真实检索并写报告；CLI 只解析参数。

```python
# metrics.py 的公开接口；ranking 每项是一条片段覆盖的 unit id 集合。
def evidence_recall(covered_units: set[str], required_units: set[str]) -> float:
    return len(covered_units & required_units) / len(required_units)

def reciprocal_rank(ranking: list[set[str]], k: int = 5) -> float:
    return next((1.0 / rank for rank, units in enumerate(ranking[:k], 1) if units), 0.0)
```

先加入下列指标测试，再实现 metrics；数据校验保证 evidence_recall 不接收空 required_units，无答案由 runner 分开统计：

```python
from noteagent.rag_eval.metrics import evidence_recall, reciprocal_rank

def test_partial_evidence_and_duplicate_hits():
    covered = set().union({"u1"}, {"u1"})
    assert evidence_recall(covered, {"u1", "u2"}) == 0.5

def test_rank_uses_first_actual_evidence():
    assert reciprocal_rank([set(), {"u1"}, {"u1"}]) == 0.5
    assert reciprocal_rank([set(), set()]) == 0.0
```

- [x] 先写有意义的单测：两个 unit 只找到一个计 0.5；重复 chunk 不加分；相同文件错误章节计 0；第二名首次命中 MRR 为 0.5；无答案不进入正例 Recall 分母。
- [x] 校验上述坏标注均被拒绝，然后实现数据读取和评分。
- [x] 基线调用真实 RetrievalService。旧 chunk 无偏移时用与当前 splitter 相同的切分设置及 start-index 辅助映射；重复文本保留全部合法位置，无法可靠定位的项标记 mapping_error，不能猜测或静默跳过。
- [x] 每个 run 在 `var/evals/rag/<run-id>/` 新建独立 Chroma，collection 与 corpus/model/chunker 配置绑定。禁止复用生产路径，禁止往不同 embedding 的同一个 collection 混写。
- [x] warmup 5 次后对 dev 每个查询重复 3 次测热延迟，性能记录与一次确定性质量结果分开；记录硬件、实际模型版本、距离度量、归一化、token 上限及截断情况。
- [x] 产出 `config.json`、`results.jsonl`、`summary.json`、`report.md`。包括 git commit/dirty 状态、语料及查询哈希、依赖版本、全部命中内容/位置/距离、逐类指标、失败分类和数据审查状态。
- [x] 报告放 `evals/rag/results/<run-id>/`，原始向量和模型缓存留在 var；不归档密钥。

待实现 CLI 契约和验证命令：

```powershell
uv run pytest tests/unit/test_rag_eval.py tests/integration/test_retrieval_service.py -q
uv run python scripts/eval_rag.py --corpus evals/rag/corpus/v1 --queries evals/rag/queries.v1.jsonl --split dev --variant baseline --run-id rag-v1-baseline-dev
```

**完成条件：** 不修改当前生产算法即可复现基线；结果不预设通过。不索引资料目录 README/sources/标注文件，只索引 manifest 指定的 notes。

## 4. 任务四：建立真实 Agent 基线

**新增：** `scripts/eval_rag_agent.py`、`src/noteagent/rag_eval/agent_run.py`、`tests/unit/test_rag_agent_eval.py`。
**复用：** `chat/agent.py`、`chat/tools.py`、`chat/citations.py`、现有 `prompt_eval/run.py` 的工具轨迹收集模式。

- [x] 确定性单测使用 fake LLM 检查评测器是否正确收集轨迹；质量运行使用真实 ChatAgent、真实工具和真实检索，不用 _FakeRetrieval。
- [x] 每个 case 独立会话和笔记副本；沿用现有评测的存储隔离方式。若需要 PostgreSQL，要求显式评测 DSN 并检查与应用 DSN 不同，缺失时将 Agent 运行标为 blocked，不能连接应用库补跑。
- [x] 记录用户输入、前置对话、工具名称与参数、检索片段、read_file 内容、最终回答、引用、待审草稿和耗时。
- [x] 历史匹配场景检查 search → read_file(目标) → propose_note 的因果顺序，允许中间出现 list_files 或补充搜索；不锁死所有工具的完整顺序。
- [x] 不把“调用了检索”直接算任务完成。回答检查事实与引用，补充检查目标、action、重复/冲突处理、原有内容保留。
- [x] 每个场景真实运行 3 次，报告逐次结果及波动；普通任务不自动审批。审批/拒绝后的索引一致性使用独立确定性集成测试。
- [x] 自动评分先完成工具/action/路径等确定性检查；语义结论保留具体证据并标注自动审查。生成一份人工抽查清单，不让执行模型将自评全部通过写成独立验收。

```powershell
uv run pytest tests/unit/test_rag_agent_eval.py tests/unit/test_chat_tools.py -q
uv run python scripts/eval_rag_agent.py --cases evals/agent/rag_cases.v1.jsonl --corpus evals/rag/corpus/v1 --split dev --variant baseline --repeat 3 --run-id agent-v1-baseline-dev
```

**完成条件：** 每条失败可归入调用缺失、查询不清、笔记缺信息、切块问题、召回问题、结果使用问题、运行错误之一，保留次要原因。运行失败不计通过，也不伪装成相关性失败。

## 5. 任务五：先处理基础笔记的真实缺陷

**新增（仅存在缺陷时）：** `evals/rag/corpus/v2/`；**复用：** `docs/evaluations/note-quality.md` 与现有正文评测脚本。

- [ ] 对任务三、四的失败逐条回查来源：答案原来就没有时，不归因于 embedding。
- [ ] 有来源的笔记按现有任务匹配、忠实、完整标准修订；无来源的笔记不凭模型记忆补事实，将待核验内容明确标出或排除相关正例。
- [ ] 改进标题指代、缺失条件、错放段落；不往正文植入评测问题、答案关键词堆叠或重复标题。
- [ ] 保留 v1，v2 记录逐篇 diff 和修订理由。证据位置重新定位，问题意图保持不变；无法一一映射的查询单列，不强行做分数对比。
- [ ] 用同一基线模型/切分/检索配置比较 v1 与 v2，报告笔记修复自身的效果；之后选定一个语料版本冻结，供后续技术实验使用。
- [ ] 只有发现生成链路反复产生相同缺陷才调整生成 prompt；调整后复跑相关正文样例。高质量人工修订语料的效果不能宣称为自动笔记生成已改善。

**完成条件：** 标准形成两份可复用内容：正文质量沿用原准则；检索质量由证据与任务集定义。没有实际内容缺陷时，记录证据并跳过 v2，不为完成步骤硬改笔记。

## 6. 任务六：按章节改进切块并验证

**修改：** `retrieval/chunker.py`、`models.py`、`service.py`、相关单测和集成测试。

- [x] 先以真实失败写回归用例：标题与正文分离、定义与限制分离、代码围栏中的 # 被误判为标题、长代码/表格、重复段落偏移。
- [x] 在现有字符切块外增加 Markdown 章节识别；短章节保留整体，长章节继续递归切分。保留原 split(content) 返回字符串列表的兼容入口，新建 split_with_metadata(content) 供索引调用。
- [x] chunk 数据包括 content、heading_path、start_char、end_char；metadata 增加这些值及 note_id、内容版本/hash。heading_path 在 Chroma 中存字符串，偏移存整数，避免不支持的复杂 metadata 类型。
- [x] 区分用于 embedding 的文本和用于引用的原文。embedding 文本可以加标题路径；引用内容必须可映射回原文，不把添加的标题误当连续原文。
- [x] 实测 tokenizer 长度，包含标题与特殊 token 的预算。每个候选模型输入都记录是否截断；超长代码/表格分段并保留来源位置，不允许为保持整块而静默截断。
- [x] 固定模型、距离、归一化和 top-k，在 dev 比较原切块与章节切块；最多比较两种长度预算，避免一次引入大量参数。
- [x] 同时复核引用和更新/删除流程。章节方案无收益时保留基线并记录失败分析。

```powershell
uv run pytest tests/unit/test_chunker.py tests/integration/test_retrieval_service.py tests/unit/test_citations.py -q
uv run python scripts/eval_rag.py --corpus evals/rag/corpus/v1 --queries evals/rag/queries.v1.jsonl --split dev --variant heading --run-id rag-v1-heading-dev
```

若任务五选定 v2，命令统一替换 corpus 为 v2，并使用同步更新证据位置的 `queries.v2.jsonl`；不得 v2 正文配 v1 偏移。

## 7. 任务七：比较向量模型，按收益决定切换

**修改：** `retrieval/embedder.py`、`bootstrap/settings.py`、评测 variant 配置；仅候选胜出后修改应用默认配置及部署依赖。

- [x] 当前实际模型作为 baseline，新增至多两个候选：一个中文轻量模型、一个多语言模型。执行时查看官方模型卡，记录完整模型 id/revision、语言、输入上限、query/document 指令、维度、资源需求、许可；BGE-M3 可列为候选，不预设胜出。
- [x] 使用相同冻结语料、章节逻辑、查询集和候选数。主比较使用所有候选均容纳的输入预算；更长上下文的潜在收益另开实验，不能归为纯模型收益。
- [x] 文档和查询使用同一模型及其正确的编码指令。距离度量与归一化遵循相应模型要求并完整记录，不继承旧距离阈值。
- [x] 每个模型新建 collection，全部重建。即使维度相同也不能混用旧向量。
- [x] 在 dev 对比 Recall@5、Hit@3、MRR、截断数、热查询 p95、索引耗时和内存。胜出定义：满足硬门槛、主要召回指标提高且其他指标无明显回退；接近持平时选择资源开销较低且运维简单的配置。
- [x] 最大验证 3 个模型（含基线），不无限追榜单。若都不达标，分类失败后进入任务八或报告语料/标注问题。
- [x] 胜出后检查 bootstrap、Dockerfile、compose、模型缓存预下载等实际配置入口，避免只改 Python 默认值却仍加载旧模型。

```powershell
uv run python scripts/eval_rag.py --corpus evals/rag/corpus/v1 --queries evals/rag/queries.v1.jsonl --split dev --variant candidate-a --run-id rag-v1-candidate-a-dev
```

**交付：** 模型对比表、采用/不采用理由、索引版本校验与回退说明。不因计划要求“优化”强行替换模型。

## 8. 任务八：按失败原因改善工具检索与 Agent 使用

**可能修改：** `retrieval/service.py`、`chat/tools.py`、`chat/prompts/system.txt`、`chat/citations.py`；按确切需要修改 `vector_store.py`。

按下面顺序，每次只增加一个因素并重跑 dev：

1. **结果不可操作：** 在 fragments 中始终返回 file_name、heading_path、原文 content 和位置，保留 source_id；无引用 registry 时仍能知道目标文件。模型不得靠解析 source_id 猜文件名。
2. **该调用却没调用/查询省略：** 补充工具说明或最少量 prompt 规则，让 Agent 结合上下文形成主题明确的 query；无需额外分流模型。
3. **命中后使用错误：** 对补充旧知识明确先 read_file 再提案；引用只能来自实际读到的证据；未找到时明确说明。已有冲突由 Agent 提出澄清或有依据的更正草稿。
4. **第 4–5 名有答案但工具只给 3 条：** 对比返回 3 和 5 条及 token 成本。最终报告必须测实际生产返回数量，不能用 Recall@5 掩盖只返回 3 条时的失败。
5. **精确词始终漏召回：** 才做关键词加向量的候选融合实验。中文分词、英文术语和去重规则写清；可用名次融合，不直接相加不同比例的原始分数。新增依赖前说明必要性。
6. **候选内有证据但排名低：** 才做 rerank 实验，分别记录重排前候选召回和重排后命中，计入模型资源与延迟。

- [x] 每项先添加对应失败的回归检查，再最小实现，记录前后对比。
- [x] 空检索结果和工具执行错误返回不同状态；Agent 不把错误说成“没有笔记”。（行为本来就分开：`{error}` 与空 `fragments` 是两种返回，已在 chat-tools.md 写明；但**没有专门的失败用例覆盖它**，属未验证。）
- [x] 无答案处理首先评价 Agent 是否识别证据不足。只有开发集能验证有效时才加相似度阈值；阈值按模型与距离校准，不写通用神奇常数。
- [x] 仍保留 Chroma。只有实测容量、延迟或一致性瓶颈指向数据库时，单列证据和后续迁移建议，不在本计划直接扩大迁移范围。

**逐项结果（2026-09-25）：**

| 项 | 状态 | 证据 |
|---|---|---|
| 1 结果不可操作 | ✅ 已做 | 片段始终带 `file_name`/`heading_path`/`start_char`/`end_char`（提交 413df7c）；检索调用率门槛口径 18/18；靠 `read_file` 兜回 4/30 → 2/30 |
| 2 该调用却没调用 | ✅ 效果达成，未改提示词 | 由第 1 项的定位信息带动：真正依赖检索的场景 100%（≥90%） |
| 3 命中后使用错误 | ✅ 已做 | 提示词 v10（提交 0ba3fa7）：冲突场景 a06 由 0/3 到 3/3；「未找到」在修正判定口径后已是 6/6 |
| 4 只给 3 条 | ⏭️ 按停止条件跳过 | e5 之后 holdout 的 Hit@3 已是 11/12，`top_k=3` 不再是瓶颈；且检索层两项硬门槛已达标 |
| 5 关键词融合 | ⏭️ 未启动 | 触发条件是「精确词始终漏召回」，当前失败样例里没有这一类 |
| 6 rerank | ⏭️ 未启动 | 触发条件是「候选内有证据但排名低」，换模型后只剩 1 条属于此因（dev），不值得引入重排资源 |

第 4–6 项都属「增加检索组件」，按停止条件不启动；若后续在真实使用中出现对应的失败样例，再单列实验。返回条数只报了实际生产口径（3 条）下的指标，没有用 Recall@5 掩盖。

**停止条件：** 达到质量门槛且性能满足约定即停止增加检索组件。未达标也要保留最佳稳定版本，不把失败候选默认发布。

## 9. 任务九：验收、重建路径与交接

**更新：** `docs/architecture/retrieval.md`、`docs/evaluations/rag-quality.md`、`evals/rag/README.md`、`evals/agent/README.md`、`scripts/README.md`；只根据实际证据更新路线图状态。

- [x] 固定候选配置，在同一冻结 corpus 和 holdout 上运行 baseline 与 selected 的直接检索和 Agent 场景；基线若早先使用其他语料，此处补跑同语料对照。报告 dev/holdout 分开，不能只展示合并平均分。
- [x] 执行新增评测器测试，以及受影响的 chunker、retrieval、tools、citations、drafts、notes API 测试；fake 测试只证明工程行为，真实检索与真实 Agent 报告证明质量。
- [x] 验证索引一致性：相同文件重复索引无无限重复；长笔记改短无旧块；删除不再命中；拒绝草稿索引不变；索引失败不破坏正式 Markdown；新旧模型配置不匹配时明确要求重建。
- [x] 模型/切块变更准备独立全量重建命令及 dry-run：显式输入 notes 根、目标索引路径、collection/版本；先在评测副本验证，再交付真实数据使用说明。
- [ ] 新索引准备好后才切换；旧索引保留供回退。真实笔记重建/生产切换不包含在评测命令中，执行者不得顺带删除旧库。

  > 重建方案已交付（报告 §6.4：`index_notes.py --all --dry-run` 先看清单、再 `--all` 重建；回退是改回 `EMBEDDING_MODEL`/`CHUNK_STRATEGY`/`EMBED_HEADING_PREFIX` 后重建）。**本次没有执行生产切换、没有动 `notes/` 与 `chromadb_persist`**，按约定由用户执行。
- [x] 输出 `docs/evaluations/rag-v1-report.md`：基础语料来源与审查情况、精确定义的指标、基线、各次对照、最终配置、失败样例、执行命令、资源/费用、未完成项、回退方法。
- [x] 抽查全部失败样例和至少 5 条通过样例。自动证据检查可以立即执行；未取得独立人工审查时明确写“工程验证完成，语义审查待确认”，交付集中审查材料。

最终验收命令（参数对应最终冻结版本，若仍使用 v1 则如下）：

```powershell
uv run python scripts/eval_rag.py --corpus evals/rag/corpus/v1 --queries evals/rag/queries.v1.jsonl --split holdout --variant selected --run-id rag-v1-selected-holdout
uv run python scripts/eval_rag_agent.py --cases evals/agent/rag_cases.v1.jsonl --corpus evals/rag/corpus/v1 --split holdout --variant selected --repeat 3 --run-id agent-v1-selected-holdout
uv run pytest tests/unit/test_rag_eval.py tests/unit/test_rag_agent_eval.py tests/unit/test_chunker.py tests/unit/test_chat_tools.py tests/unit/test_citations.py tests/unit/test_drafts.py tests/integration/test_retrieval_service.py tests/integration/test_notes_api.py -q
```

## 10. 实验纪律与交付节奏

每次实验记录：假设 → 只改变什么 → 固定什么 → 结果 → 失败例 → 采用/回退。基线与新结果必须使用同一组可比数据；数据版本变化单列比较。

建议分三批提交，避免一次大改无法判断收益：

1. **基础建设：任务 1–4。** 交付语料、查询/任务集、指标、两个评测入口及真实基线。即使 baseline 不达标，本批也可以按“评测基础完成”交付。
2. **有依据的优化：任务 5–8。** 每项独立记录对照；笔记→切块→模型→工具策略逐步推进，保留有效改动。
3. **验收交接：任务 9。** 交付未见数据结果、运行文档、重建/回退方案和明确限制。

每批结束报告完成项和下一步；在授权范围内继续执行，不把例行进度报告当成反复请求许可。需要用户判断的语义标注集中成一份清单，其余工程工作继续。

## 可直接交给 Claude Code 的执行指令

```text
请执行 docs/plans/2026-09-25-rag-quality-improvement.md。
先阅读 CLAUDE.md 和计划引用的现行文档，保留当前未提交修改。
本次 RAG 定位为 Agent 按需调用的历史笔记检索工具，用于回忆知识及匹配补充旧笔记。
按计划先复用现有笔记建立隔离语料，再建立证据标注、指标和真实基线，然后依据失败样例逐项优化。
任务 1–4 先完成；任务 5–8 按诊断与停止条件推进；最后完成任务 9。
不要预先更换向量数据库，不要同时更改所有组件，不要把 fake retrieval 或自评当作真实质量验收。
运行计划要求的测试和评测，记录实际命令、结果、数据/模型版本和未完成项。
API/模型下载不可用时完成离线部分并清楚报告阻塞；不要伪造分数或默默使用生产数据路径。
逐项勾选计划，分阶段总结并继续推进；将需要人工核对的语义问题集中交付。
最终给出指标前后对照、保留方案、失败样例，以及安全的索引重建和回退说明。
```
