# evals

评测的**唯一入口**：准则、汇总报告、三类评测数据与运行结果都在本目录管理。不要把私人笔记全文放进来。

| 放什么 | 路径 |
|--------|------|
| 准则、指标、计分规则、报告契约 | [criteria/](criteria/) |
| 汇总报告、复盘、阶段验收 | [reports/](reports/) |
| 黄金集（考题）、语料与 fixture | [prompt/](prompt/README.md)、[rag/](rag/README.md)、[agent/](agent/README.md) |
| 离线跑分结果 | 各数据目录下的 `results/` |

评测**不是**运行时模块：不在 `POST /chat` 上拦截草稿，不按分数自动再生成，不把分数写入 `notes/`。产品路径仍是提案 → 人审 → 落盘。尺子是给以后**离线迭代** [`system.txt`](../src/noteagent/chat/prompts/system.txt) 用的。

架构书里的索引：[architecture.md 第 6 节](../docs/architecture/architecture.md#6-评测)。

## criteria（现行准则）

| 文件 | 内容 | 状态 |
|------|------|------|
| [criteria/note-quality.md](criteria/note-quality.md) | 笔记正文质量 v0.2：三道硬门、五个 0–4 维度、知识加工增益与证据契约、校准集契约 | 现行准则 |
| [criteria/rag-quality.md](criteria/rag-quality.md) | 检索（RAG）v1：语料、证据标注契约、九项指标、失败分类与报告契约 | 现行准则 |

旧 [`prompt/cases.jsonl`](prompt/cases.jsonl) 仍按 v0.1 六维小指标计 `total`；学习型 [`prompt/learning_notes.jsonl`](prompt/learning_notes.jsonl) 走 v0.2 硬门 + Judge。

## reports（报告与复盘）

| 文件 | 内容 | 状态 |
|------|------|------|
| [reports/rag-v1-report.md](reports/rag-v1-report.md) | RAG v1 实测报告：最终验收（dev + holdout）、各次对照、失败样例、重建 / 回退。含 2026-09-27 的 §1.1 dev 数字勘误 | 已交付（2026-09-25） |
| [reports/v1-acceptance-report.md](reports/v1-acceptance-report.md) | V1 收尾：审批写盘异常修复、25 条生成验收样例实跑、自动测试与旧集回归 | 已交付（2026-09-26）；V1 已验收，手动功能验收由用户执行并反馈通过（未逐项留证） |
| [reports/rag-v1-retrospective.md](reports/rag-v1-retrospective.md) | 检索质量这一轮的复盘：问题（产品侧 7 条、评测侧 6 条）、做法、结果、不足与后续触发条件 | 历史记录（2026-09-25） |

工具 / Agent 轨迹的分析报告以后同样写进 `reports/`：该不该 `propose_note`、工具顺序、create/append/replace/delete。数据用 [agent/](agent/README.md) 与 prompt 集里的 behavior 条。

**三本账不要合成一个 Agent 总分**：改提示词看笔记正文分；改工具策略看行为门；改切块 / embedding 看 RAG。

## 三类数据与运行产物

| 目录 | 用途 |
|------|------|
| [prompt/](prompt/README.md) | 系统提示 / 笔记正文考题（`cases.jsonl` 20 条 + `learning_notes.jsonl` 的 `l01`）+ 意图门 behavior 条；结果在 [prompt/results/](prompt/results/README.md) |
| [rag/](rag/README.md) | 冻结语料 v1（10 篇）+ 40 条带证据标注的检索查询；结果在 `rag/results/` |
| [agent/](agent/README.md) | 20 条真实 `ChatAgent` 场景（调用时机、结果使用、引用、写入安全）；结果在 `agent/results/` |

检索与 Agent 语料的**正文不进仓库**（与 `notes/*` 同一隐私口径）：只提交 manifest 哈希、审查摘要与不含正文的报告结论，完整版在 `var/evals/rag/`。

`results/`、`config.json`、manifest、案例与 prompt 副本是**运行证据**：保持原样可追溯，不因文档搬迁而改写，也不重新评分。报告的身份（日期、提交、run ID、模型配置、分母、失败样例）与历史成绩不得因整理而改变。

## 怎么跑

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03 --prompt src/noteagent/chat/prompts/system.txt
python scripts/eval_notes.py --name v9 --judge --cases evals/prompt/learning_notes.jsonl --ids l01
python scripts/calibrate_learning_notes.py

# 检索与 Agent（真检索 / 真 ChatAgent；独立语料与索引）
python scripts/eval_rag.py --split dev --variant baseline --run-id rag-v1-baseline-dev
python scripts/eval_rag_agent.py --split dev --variant baseline --run-id agent-v1-baseline-dev --repeat 3
```

进程内 `ChatAgent`（`CHAT_MODEL` + 四工具），临时 notes / SQLite，不启动 HTTP，不人审写盘。无 `DEEPSEEK_API_KEY` 时退出码 1。

每条先过 **行为门**，再评笔记正文（仅实际提案时评 `content`）：

1. 是否调用了 `propose_note`，是否与 `expect_propose` 一致。该提案时，`list_files` 是否出现在 `propose_note` 之前（见 `expect_tools_prefix`）。
2. 草稿 `content` 是否包含全部 `must_headings`（原文含编号）；是否出现 `forbidden_headings`。
3. 是否包含全部 `must_anchors`。
4. `content` 是否以 `# ` 当正文一级标题（结构扣分）。
5. `style` 为 `faithful_paragraphs` 时，主体应是段落；`outline` 允许短列表；`excerpt` 不应出现未点名的其它大节标题。材料里有代码/命令/REPL/备注时，草稿须有围栏或 `>` 引用（n03 / n08 另见 `must_substrings`）。

行为失败与正文分两列记，不混成一个 Agent 总分。失败则记下 id，只改一类 prompt，归档 `prompts/iterations/vN`，再跑同一集。学习型题的硬门、维度和校准契约见 [criteria/note-quality.md](criteria/note-quality.md) §6 与 [prompt/README.md](prompt/README.md)。

## 字段

`id`、`kind`（quality|behavior）、`user`、`expect_propose`、`expect_tools_prefix`、`must_headings`、`forbidden_headings`、`must_anchors`、`must_substrings`（可选）、`style`、`expect_action`（可选）、`seed_files`（可选，评测开始前写入临时 notes）。学习型题另有 `task_mode`、`must_concepts`、`review_questions` 等字段，见 [prompt/README.md](prompt/README.md)。

## 校准历史（证据）

语义 Judge 缺失或解析失败会标为未完成；生成模型与 Judge 模型相同时必须记 `judge_independent=false`，不构成独立校准。契约细节见 [criteria/note-quality.md](criteria/note-quality.md) §5–§6。

2026-09-10 同模型四候选校准（`deepseek-v4-flash`，[`calibration_l01_20260910-135238-835257`](prompt/results/learning_notes/calibration_l01_20260910-135238-835257/)，`judge_independent=false`）暴露：Judge 给 `good` / `literal` 的 `fluent` 均为 4，仅旧的「优秀 fluent 严格高于机械译文」契约失败。标准据此修正为**双方 fluent 均须达阈值**，结构与加工增益仍要求优秀领先；Judge 与 fixtures 未为通过契约而改动。同日 v9 生成 + Judge（[`v9-learning_l01_20260910-215727`](prompt/results/learning_notes/v9-learning_l01_20260910-215727/)）硬门与复习题通过，structure 2/4、processing 1/4，不合格。生成提示词此后于 2026-09-25 升到 v10（用户要更正时先指出冲突再问）、2026-09-26 升到 v11（草稿面板措辞），现行版本见 [prompts/README.md](../src/noteagent/chat/prompts/README.md) 与 [iterations/](../src/noteagent/chat/prompts/iterations/README.md)。

字符比、句子边界重合度和标题数量均不能用作语义质量代理。单个 Python 教程样本只用于第一阶段校准，不表示对所有教程的泛化能力。

## 边界

- **不要放进 `tests/`。** `tests/` 是无网络、无真实 LLM 的 pytest。本目录的一键脚本不进默认 CI。
- 不要让写草稿的同一个模型给自己打分。
- 不要往 `notes/` 回流生成结果。
- 不要把私人笔记全文写进黄金集。
