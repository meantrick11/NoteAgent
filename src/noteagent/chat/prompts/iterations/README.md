# 系统提示词迭代集

运行时只读上一级 [`system.txt`](../system.txt)。本目录是归档，**不要**改 `ChatAgent` 去加载这里的文件。

从 `system.txt` 入库到现在一共 **9 版**。

| 版 | 日期 | 来源 | 文件 | 改了什么 |
|----|------|------|------|----------|
| v1 | 2026-08-20 | `6fff35c` | [v1-2026-08-20-initial.txt](./v1-2026-08-20-initial.txt) | 首版：读 `context.md`；「信息足够就提案」；正文强制 `##` + 要点 ≤30 字、标题自行归纳不照抄 |
| v2 | 2026-08-31 | `4fb276b` | [v2-2026-08-31-context-injection.txt](./v2-2026-08-31-context-injection.txt) | 短期记忆落地：删 `context.md` 首轮附带，改为系统注入历史摘要与近期对话。正文格式未动 |
| v3 | 2026-08-31 | `dd3fe04` | [v3-2026-08-31-intent-and-faithful.txt](./v3-2026-08-31-intent-and-faithful.txt) | 意图门（先问再提案）；取消口号式短要点；按材料忠实组织；标题「按主信息生成」但仍允许模型自拟骨架 |
| v4 | 2026-09-01 | 标题树 | [v4-2026-09-01-heading-tree.txt](./v4-2026-09-01-heading-tree.txt) | 原标题含编号照抄并映射 `##`/`###`/`####`；禁止合并/自拟标题 |
| v5 | 2026-09-01 | 五要素+六条 | [v5-2026-09-01-five-elements.txt](./v5-2026-09-01-five-elements.txt) | Role/Context/Task/Constraint/Example；Constraint 写入忠实/完整/结构/流畅/形态/可检索 |
| v6 | 2026-09-01 | Markdown 写法 | [v6-2026-09-01-md-syntax.txt](./v6-2026-09-01-md-syntax.txt) | 形态合适：围栏代码、行内 code、`>` 引用、块间空行。与当时 `system.txt` 相同 |
| v7 | 2026-09-01 | 写模式 | [v7-2026-09-01-replace-delete.txt](./v7-2026-09-01-replace-delete.txt) | `propose_note` 增加 replace（整文件覆盖）与 delete；模型先判断 append/create/replace/delete |
| v8 | 2026-09-05 | 一层目录 | [v8-2026-09-05-one-level-folders.txt](./v8-2026-09-05-one-level-folders.txt) | `file_name` 可为 `Folder/Note.md`；list_files 带文件夹；禁止擅自 mkdir。与当时 `system.txt` 相同 |
| v9 | 2026-09-10 | 学习型笔记 | [v9-2026-09-10-learning-notes.txt](./v9-2026-09-10-learning-notes.txt) | 默认学习型笔记；语义忠实与覆盖；允许有依据的重组；新增知识加工增益。与现行 `system.txt` 字节一致 |

加新版时：复制当时的 `system.txt` 为 `vN-日期-短名.txt`，在本表追加一行，不要改旧档。人工回归见 [evals/prompt/](../../../../../evals/prompt/README.md)。

## v8 问题与 v9 修正

v8 在 `Whetting Your Appetite` 样本上退化为逐段译文：忠实、完整被原标题、句段数量等表面形式化；系统提示与运行时材料标题树形成双重硬约束，要求原标题原样成为输出标题并禁止另造标题，压制了语义分组和关系显式化。

v9 将普通“记下来/整理成笔记”和“翻译并整理为笔记”定义为学习型笔记，只有显式要求完全忠实翻译、逐段翻译或保持原结构时才沿用原结构。完整度改按语义单元覆盖判断，标题树只标记覆盖范围与章节边界；新增第七条“知识加工增益”，同时保留工具、人审、写模式、引用、Markdown 与安全约束。

评测集固定为 [`evals/prompt/learning_notes.jsonl`](../../../../../evals/prompt/learning_notes.jsonl)。运行：

```bash
python scripts/eval_notes.py --name v9 --judge --cases evals/prompt/learning_notes.jsonl --ids l01 --prompt src/noteagent/chat/prompts/system.txt
```

Judge 留痕写入该次结果目录：`config.json` 记录生成模型、Judge 模型、生成 Prompt SHA-256、Judge 配置与 `judge_independent`；每题 Markdown 记录评分、理由及原文/草稿证据。Judge 缺失或解析失败时必须标记“未完成”，不得生成摊权后的分数。

2026-09-10 用 deepseek-v4-flash 对四固定候选做同模型校准（`judge_independent=false`）：good/literal 的 fluent 均可为 4，结构/加工/维度总和区分仍成立。校准契约已从「优秀 fluent 严格高于机械译文」改为双方 fluent 均须达阈值；优秀靠结构和加工增益领先。早期失败跑次（非逐字证据、协议外字段）按设计留痕，未放宽契约。通过结果在 [`evals/prompt/results/learning_notes/calibration_l01_20260910-135238-835257/`](../../../../../evals/prompt/results/learning_notes/calibration_l01_20260910-135238-835257/)。正式 Prompt 比较仍应固定与生成模型不同的独立 `JUDGE_MODEL`。

v9 对 `l01` 的 `--judge` 实跑（[`v9-learning_l01_20260910-215727`](../../../../../evals/prompt/results/learning_notes/v9-learning_l01_20260910-215727/)）：行为门通过，三道硬门通过，复习题 8/8；`qualified=false`（structure 2/4、processing 1/4、fluent 4/4）。草稿仍是按原文顺序的译文。v9 是现行生成提示词，不是已合格版本。
