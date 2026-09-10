# evaluations

评测的**准则与账本划分**写在本目录。黄金集和以后的跑分产物不放这里。

| 放什么 | 路径 |
|--------|------|
| 准则、指标、计分规则、报告契约 | 本目录 |
| 黄金集（考题） | 仓库根 [`evals/`](../../evals/README.md) |
| 离线跑分结果 | [`evals/prompt/results/`](../../evals/prompt/results/README.md) |

评测**不是**运行时模块：不在 `POST /chat` 上拦截草稿，不按分数自动再生成，不把分数写入 `notes/`。产品路径仍是提案 → 人审 → 落盘。尺子是给以后**离线迭代** [`system.txt`](../../src/noteagent/chat/prompts/system.txt) 用的。

架构书里的索引：[architecture.md 第 6 节](../architecture/architecture.md#6-评测)。

## 包含模块

| 文件 | 内容 | 状态 |
|------|------|------|
| [note-quality.md](./note-quality.md) | 笔记正文质量 v0.2：三道硬门、原六维、知识加工增益与证据契约 | 现行准则 |
| 工具 / Agent 轨迹 | 该不该 `propose_note`、工具顺序、create/append/replace/delete | 以后写本目录；数据仍用 [`evals/agent/`](../../evals/agent/README.md) 与 prompt 集里的 behavior 条 |
| RAG | Recall、命中文件/章节、引用 | 以后写本目录；数据在 [`evals/rag/`](../../evals/rag/README.md)（尚空） |

三本账**不要合成**一个 Agent 总分。改提示词看笔记正文分；改工具策略看行为门；改切块/embedding 看 RAG。

## 基础使用

写或改记笔记提示词时，对照 [note-quality.md](./note-quality.md) 与 [`evals/prompt/cases.jsonl`](../../evals/prompt/cases.jsonl)。学习型笔记还要使用 [`evals/prompt/learning_notes.jsonl`](../../evals/prompt/learning_notes.jsonl) 和四个固定候选。跑分：

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v9 --judge --cases evals/prompt/learning_notes.jsonl --ids l01
python scripts/calibrate_learning_notes.py
```

不要把私人笔记全文写进黄金集。`tests/` 仍只跑无网络单元测试；本脚本不进默认 CI。

## v0.2 校准边界

学习型笔记先过任务匹配、忠实、完整三道硬门，任一失败都不能给出合格结论。四候选的人工排序契约是 `good > literal > omitted`，而 `hallucinated` 必须因无来源命题被忠实硬门淘汰。优秀与机械译文都应达到流畅阈值；优秀靠结构和加工增益领先，流畅度不是知识加工的区分轴。

运行固定候选校准：

```bash
python scripts/calibrate_learning_notes.py
```

校准 fixture 是版本化的评测固定输入，不是用户笔记，也不应被运行时读取。学习型评测可用 `--judge` 启用语义 Judge；缺失或解析失败会明确标为未完成。未配置 `JUDGE_MODEL` 时，校准和 `--judge` 会警告并使用 `CHAT_MODEL`，且记录 `judge_independent=false`；这种同模型结果只适合初步自检。正式 Prompt 比较应固定一个与 `CHAT_MODEL` 不同的 `JUDGE_MODEL`。

2026-09-10 同模型四候选校准（deepseek-v4-flash，`judge_independent=false`）暴露：Judge 给 good/literal 的 fluent 均为 4，仅旧的「优秀 fluent 严格高于机械译文」契约失败。标准已修正为双方 fluent 均须达阈值，结构、加工与维度总和仍要求优秀领先；Judge 与 fixtures 未为通过契约而改动。通过结果：[`calibration_l01_20260910-135238-835257`](../../evals/prompt/results/learning_notes/calibration_l01_20260910-135238-835257/)。

同日 v9 生成 + Judge（[`v9-learning_l01_20260910-215727`](../../evals/prompt/results/learning_notes/v9-learning_l01_20260910-215727/)）：硬门与复习题通过，structure 2/4、processing 1/4，不合格。现行 [`system.txt`](../../src/noteagent/chat/prompts/system.txt) 仍是 v9。

字符比、句子边界重合度和标题数量均不能用作语义质量代理。单个 Python 教程样本只用于第一阶段校准，不表示对所有教程的泛化能力。
