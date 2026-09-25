# 检索（RAG）质量准则与指标（v1）

本文是离线评价 **历史笔记检索** 的契约：数据集形状、证据标注规则、指标定义与报告要求。它与 [note-quality.md](./note-quality.md) 分工不同，**不得互相替代**：

| 准则 | 评什么 | 不评什么 |
|------|--------|----------|
| [note-quality.md](./note-quality.md)（v0.2） | `propose_note` 生成的 Markdown 正文质量 | 检索、工具、索引 |
| 本文（v1） | 检索是否召回正确证据、Agent 是否正确调用与使用检索、引用能否追溯 | 正文写得好不好 |

两者共用的只有语料事实源。**检索指标不能用来给正文质量打分**；反过来，正文质量分也不能证明召回效果。

架构见 [architecture/retrieval.md](../architecture/retrieval.md)，Agent 工具边界见 [architecture/chat-tools.md](../architecture/chat-tools.md)。

---

## 1. 定位：Agent 按需调用的历史笔记检索

RAG 在本项目里不是独立问答服务，而是 Agent 的一个工具：回忆旧知识，以及把新内容匹配到旧笔记。

```text
用户提问 → Agent 判断是否依赖历史 → search_relative_from_chromadb(query)
        → 片段 + 出处 → Agent 继续推理（可 read_file 目标全文）
        → 回答并引用 / 提案补充旧笔记（仍走人审）
```

因此评测分两层，共享冻结的语料与证据标注：

1. **直接检索层**：把查询直接交给 `RetrievalService.search`，评证据召回与排序。不含 Agent。
2. **Agent 层**：真实 `ChatAgent` + 真实工具 + 真实检索，评调用时机、结果使用、引用与写入安全。

两层都必须有**真实**运行结果。`_FakeRetrieval`、假向量或模型自评只证明工程行为，不构成质量证据。

---

## 2. 数据集位置与构建方式

| 路径 | 内容 | 进仓库 |
|------|------|--------|
| `evals/rag/corpus/v1/notes/` | 10 篇冻结笔记副本，**字节级等于原笔记** | 否（隐私，`.gitignore`） |
| `evals/rag/corpus/v1/sources/` | 可获得的原始材料 | 否 |
| `evals/rag/corpus/v1/manifest.jsonl` | 每篇 `note_id`、相对路径、sha256、原路径、来源、审查状态、已知问题 | 是 |
| `evals/rag/corpus/v1/audit.md` | 逐篇：可回答的问题、缺失上下文、已发现缺陷 | 是 |
| `evals/rag/queries.v1.jsonl` | 40 条直接检索查询与证据标注（含 `quote` 正文） | 否 |
| `evals/agent/rag_cases.v1.jsonl` | 20 条 Agent 场景（含补充内容） | 否 |
| `evals/rag/results/<run-id>/summary.md` | 指标、逐类结果、失败分类 | 是 |
| `evals/agent/results/<run-id>/summary.md` | 同上 | 是 |
| `var/evals/rag/<run-id>/` | `config.json`、`results.jsonl`（全部命中内容/位置/距离）、`report.md` 完整版、本次独立 Chroma | 否 |

**为什么正文不进仓库。** 正式 `notes/*` 已被 `.gitignore` 排除；评测语料是它的副本，`quote` 与命中记录都会逐字包含正文。仓库只保留可校验的哈希（manifest）与不含正文的结论。这是对计划的已知偏离，逐次报告需复述该限制。完整版报告落在被忽略的 `var/evals/rag/`，复核失败样例时需要本地语料。

**语料选取。** 从 `notes/` 盘点后取 10 篇，覆盖中文表达、中英术语混合、长文多章节、代码或表格、相近主题干扰（类别允许重叠）。不按文件名认定质量；排除 README、备份、日记、残稿与个人事务文件。**基线阶段不改写笔记**：先测原文，缺陷记入 `audit.md`。

**来源状态。** `source_status` 取 `available` / `missing` / `synthetic`。只有 `available` 才能核对忠实与完整；`missing` 只能判断可读性与内部一致性，不得声称已验证忠实性。

---

## 3. 单条查询的字段契约

实际内容与偏移一律从冻结语料提取，**不得填写虚构位置**。运行时校验由 `noteagent.rag_eval.dataset` 实现。

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

**偏移约定。** `start_char` / `end_char` 是 **UTF-8 解码后 Python 字符串的字符下标**（不是字节下标），范围 **左闭右开**，满足 `note_text[start_char:end_char] == quote`。语料 10 篇的换行符是 **CRLF**，偏移在原始解码文本上计算，**不做换行归一化**；草稿中多行引文用 `\n` 书写，生成脚本按笔记实际换行符定位，并存储实际切片。

**heading_path 约定。** 从笔记的 H1 到目标小节，用 `" > "` 连接各级标题文本，去掉 `#` 与首尾空格，例如：

```text
回溯算法 > 回溯法理论基础 > 什么是回溯法
Python_Tutorial_Overview > 3. Python 速览 > 3.1. Python 用作计算器
```

**证据单元。** 一个查询可有多个必需 unit；一个 unit 可有多个**可替代**位置（同一事实在别的笔记也写了）。`fact` 写明必须保留的事实或条件。证据单元必须**短于切块长度**（当前 500 字符），否则单块无法完整覆盖，指标会被切块边界而非检索质量拖累。

**必须拒绝的标注（dataset 校验失败）**：

- `evidence_units` 为空，或 unit 没有 `alternatives`；
- `start_char >= end_char`，或 `note_text[start_char:end_char] != quote`；
- `note_id` 不在 manifest，或位于被忽略的语料之外；
- 无答案（`answerable=false`）却带正证据，或有答案却无证据；
- 同一 `group_id` 跨 dev 与 holdout。

---

## 4. 数据集配比与 dev / holdout 纪律

| 集合 | 有答案 | 无答案 | 合计 |
|------|--------|--------|------|
| dev | 18 | 6 | 24 |
| holdout | 12 | 4 | 16 |
| 合计 | 30 | 10 | 40 |

有答案的 30 条按类别分配：直接事实 8、同义改写 8、中英术语 6、跨段或多证据 8（8+8+6+8=30）。

- 相同信息需求的不同问法用**同一个 `group_id`**，整组只进入一种 split，避免同一问题两边各出现。
- 无答案样例必须核查**整个语料**，其中至少一半包含与已有内容相近的术语：允许召回相关背景，但不能判为回答证据。
- 无答案不等于「语料里没有这个词」。判断依据是：语料没有任何片段能支撑该问题的答案。

**Agent 场景**（`evals/agent/rag_cases.v1.jsonl`）：

| 场景 | dev | holdout | 合计 |
|------|-----|---------|------|
| 历史知识回答 | 4 | 2 | 6 |
| 新内容匹配并补充旧笔记 | 4 | 2 | 6 |
| 历史无答案 | 2 | 2 | 4 |
| 无需检索的普通对话 | 2 | 2 | 4 |
| 合计 | 12 | 8 | 20 |

补充场景必须给出 `new_content`、目标笔记、期望 `action`、必须保留的原有事实；至少 2 条含重复信息、2 条含需要澄清的冲突。

**纪律。** dev 用于调试；holdout 在选定候选后才使用。**一旦依据 holdout 失败修改方案，该集合即视为已见**，必须追加新的未见样本，不得反复宣称同一集合是盲测。质量门槛分别应用于 dev 与 holdout，不允许合并后掩盖 holdout 失败。

---

## 5. 指标

| 指标 | 计算方法 | 门槛/用途 |
|------|----------|-----------|
| Evidence Recall@5 | 每个有答案查询：前 5 个片段覆盖的必需 unit 数 / 全部必需 unit 数，再对查询平均 | >= 85% |
| Evidence Hit@3 | 前 3 个片段至少完整覆盖一个 unit 的有答案查询比例 | >= 80%（现行工具只返回 3 条） |
| MRR@5 | 第一个完整覆盖 unit 的片段排名取倒数，未命中记 0，再平均 | 诊断排序，无硬门槛 |
| 引用可追溯率 | 实际返回的引用中能定位回当前文件、章节与原文的比例 | 100%；无引用记 N/A，不自动满分 |
| 历史任务检索调用率 | **只统计真正依赖检索的场景（历史问答 + 历史无答案）**中确实调用检索的比例；追加场景单独报，不计入门槛 | >= 90% |
| 无需检索误调用率 | 普通对话中不必要地调用检索的比例 | <= 10% |
| Agent 任务成功率 | 回答事实正确且有依据，或补充的目标/action/内容正确且未破坏原有信息的完整任务比例 | >= 85%，按场景分别报告 |
| 历史无答案正确处理率 | 明确说明未找到历史依据、未把背景片段冒充答案的比例 | >= 90% |
| 写入与更新安全 | 未审批不写正式笔记、拒绝不改索引、替换或删除后无旧证据 | 所有确定性用例通过 |
| 性能 | 热查询 p50/p95、冷启动、建索引耗时、内存、工具返回 token 数 | 先测基线；无预先说明的取舍时，热查询 p95 不超过基线 2 倍 |

**unit 命中规则。** 同一文档中，返回片段的原文区间必须**完整覆盖**某个 alternative 的证据区间才计覆盖；同一文档的多个命中区间可以合并后判断，但只有真正交给消费者的内容才算。Hit 与 MRR 要求**单个片段**覆盖至少一个 unit。按 unit 去重，重叠块不重复加分。文件命中率只作诊断，不替代证据命中率。

**无答案查询**不进入正例 Recall 分母，单独统计。检索层当前没有相似度阈值，因此无答案的正确处理首先在 Agent 层评价（是否识别证据不足、是否把背景片段冒充答案）。只有 dev 上验证有效时才加阈值，且阈值按实际模型与距离度量校准，不写通用常数。

**Agent 层「事实正确且有依据」用确定性判定**：回答中的 `[[cite:N]]` 经 `CitationRegistry` 映射回注册的 `quote`/片段，若覆盖该 case 的必需证据单元则计有依据。不使用同模型自评作为质量认证。

**小样本报告**必须同时给出成功数/总数与百分比，逐场景展示。4 条无答案样例的 90% 门槛实际要求 4/4。LLM 评分不能替代证据核查。

**调用率分母的界定（2026-09-25 修订）**：只包含**真正依赖检索**的场景，即历史问答与历史无答案；追加场景不计入门槛，因为计划明确允许那里只走 `list_files` + `read_file`（用户已点名目标笔记时，检索不是必需步骤）。追加场景的调用率**单独报告**，用于观察而非验收：实测中它正是波动最大的一类（同一配置两次运行为 8/12 与 11/12）。每次真实运行算一次机会，另报按 case 汇总的三次成功分布。普通对话不计入历史任务成功率，其检索调用率单列为「无需检索误调用率」。相同语料与 split 下才比较新旧延迟。

---

## 6. 报告契约

每个 run 产出：

| 文件 | 内容 |
|------|------|
| `config.json` | git commit 与 dirty 状态、语料/查询集哈希、模型 id 与 revision、切块参数、距离度量与归一化、依赖版本、硬件、随机性设置 |
| `results.jsonl` | 逐 query/case 的全部命中内容、位置、距离、覆盖判定、失败分类 |
| `summary.json` | 逐类与总体指标、成功数/总数 |
| `report.md` | 完整版（含命中正文，落 `var/`）；提交版为 `summary.md`（不含正文） |

每条失败必须归入**一类主因**并保留次要原因：

```text
调用缺失 / 查询不清 / 笔记缺信息 / 切块问题 / 召回问题 / 结果使用问题 / 运行错误
```

运行失败不计通过，也不伪装成相关性失败。模型或数据缺失属于**未完成**，不得用假向量结果冒充真实检索质量。

---

## 7. 与正文质量准则的边界

- 不得用字符比、逐句对齐率、标题数量或 BLEU/ROUGE 替代检索或正文的语义结论。
- 检索指标必须锚定**人工标注的证据单元**，不能只看「返回了 3 条」。
- `note-quality.md` 的正文修订（任务 5）若改变语料，必须重建证据位置并另开数据集版本（如 `queries.v2.jsonl`）；**不得用 v2 正文配 v1 偏移做分数对比**。
