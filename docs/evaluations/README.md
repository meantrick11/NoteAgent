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
| [note-quality.md](./note-quality.md) | 笔记正文质量 v0.1：六条、小指标、分档、权重、溯源契约 | 现行准则 |
| 工具 / Agent 轨迹 | 该不该 `propose_note`、工具顺序、create/append/replace/delete | 以后写本目录；数据仍用 [`evals/agent/`](../../evals/agent/README.md) 与 prompt 集里的 behavior 条 |
| RAG | Recall、命中文件/章节、引用 | 以后写本目录；数据在 [`evals/rag/`](../../evals/rag/README.md)（尚空） |

三本账**不要合成**一个 Agent 总分。改提示词看笔记正文分；改工具策略看行为门；改切块/embedding 看 RAG。

## 基础使用

写或改记笔记提示词时，对照 [note-quality.md](./note-quality.md) 与 [`evals/prompt/cases.jsonl`](../../evals/prompt/cases.jsonl)。跑分：

```bash
python scripts/eval_notes.py --ids b06,n05
```

不要把私人笔记全文写进黄金集。`tests/` 仍只跑无网络单元测试；本脚本不进默认 CI。
