# prompts

只放提示词文本，不放 Python，不把用户笔记贴进本目录。

## 包含模块

| 文件 | 作用 |
|------|------|
| `system.txt` | **现行**系统提示（Agent 只读这一份）。结构为 Role / Context / Task / Constraint / Example；Constraint 为笔记七条质量 |
| [`iterations/`](iterations/README.md) | 历次全文归档；现为 v1–v10。v10 与现行 `system.txt` 字节一致 |

`ChatAgent` 用文件路径读取，不经过包 import：

`src/noteagent/chat/prompts/system.txt`

## 基础使用

改 `system.txt` 后**重启进程**（每次 `stream()` 会重新读该文件）。不要改 `ChatAgent` 去加载 `iterations/`。

人工黄金集（不进 pytest）：[evals/](../../../../evals/README.md)。准则：[docs/evaluations/note-quality.md](../../../../docs/evaluations/note-quality.md)。改完提示词：

```bash
python scripts/eval_notes.py --name v9 --judge --cases evals/prompt/learning_notes.jsonl --ids l01 --prompt src/noteagent/chat/prompts/system.txt
```

v8 在 `Whetting Your Appetite` 样本上会退化为逐段译文：忠实与完整被原标题、句段数量等表面形式约束，系统提示与材料标题树又同时要求原标题原样成为骨架。v9 将默认模式改为学习型笔记，以语义支持与覆盖为硬门，允许有依据的重组，并新增“知识加工增益”。

v9 使用 [`evals/prompt/learning_notes.jsonl`](../../../../evals/prompt/learning_notes.jsonl) 评测。启用 `--judge` 后，以结果目录中的 `config.json` 留存生成模型、Judge 模型、生成 Prompt SHA-256、Judge 配置及 `judge_independent`，每题 Markdown 留存评分、理由与原文/草稿证据；Judge 缺失或失败须标记未完成。

2026-09-10 同模型 Judge 实跑（[`v9-learning_l01_20260910-215727`](../../../../evals/prompt/results/learning_notes/v9-learning_l01_20260910-215727/)）：硬门与复习题通过，结构 2/4、加工 1/4，不合格。v9 的结论是下一步应只改生成提示词、不要同时改 Judge。

2026-09-25：**v10** 只在「用户明确要更正」那一行加了「与原文冲突时先指出冲突、不要直接 replace」。动因是检索评测的 `a06` 失败样例（见 [rag-v1-report.md](../../../../docs/evaluations/rag-v1-report.md) §4.1）；笔记质量用固定黄金集回归，结果见 [iterations/README.md](iterations/README.md)。
