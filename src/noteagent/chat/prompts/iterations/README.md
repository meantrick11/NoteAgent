# 系统提示词迭代集

运行时只读上一级 [`system.txt`](../system.txt)。本目录是归档，**不要**改 `ChatAgent` 去加载这里的文件。

从 `system.txt` 入库到现在一共 **7 版**。

| 版 | 日期 | 来源 | 文件 | 改了什么 |
|----|------|------|------|----------|
| v1 | 2026-08-20 | `6fff35c` | [v1-2026-08-20-initial.txt](./v1-2026-08-20-initial.txt) | 首版：读 `context.md`；「信息足够就提案」；正文强制 `##` + 要点 ≤30 字、标题自行归纳不照抄 |
| v2 | 2026-08-31 | `4fb276b` | [v2-2026-08-31-context-injection.txt](./v2-2026-08-31-context-injection.txt) | 短期记忆落地：删 `context.md` 首轮附带，改为系统注入历史摘要与近期对话。正文格式未动 |
| v3 | 2026-08-31 | `dd3fe04` | [v3-2026-08-31-intent-and-faithful.txt](./v3-2026-08-31-intent-and-faithful.txt) | 意图门（先问再提案）；取消口号式短要点；按材料忠实组织；标题「按主信息生成」但仍允许模型自拟骨架 |
| v4 | 2026-09-01 | 标题树 | [v4-2026-09-01-heading-tree.txt](./v4-2026-09-01-heading-tree.txt) | 原标题含编号照抄并映射 `##`/`###`/`####`；禁止合并/自拟标题 |
| v5 | 2026-09-01 | 五要素+六条 | [v5-2026-09-01-five-elements.txt](./v5-2026-09-01-five-elements.txt) | Role/Context/Task/Constraint/Example；Constraint 写入忠实/完整/结构/流畅/形态/可检索 |
| v6 | 2026-09-01 | Markdown 写法 | [v6-2026-09-01-md-syntax.txt](./v6-2026-09-01-md-syntax.txt) | 形态合适：围栏代码、行内 code、`>` 引用、块间空行。与当时 `system.txt` 相同 |
| v7 | 2026-09-01 | 写模式 | [v7-2026-09-01-replace-delete.txt](./v7-2026-09-01-replace-delete.txt) | `propose_note` 增加 replace（整文件覆盖）与 delete；模型先判断 append/create/replace/delete。与现行 `system.txt` 相同 |

加新版时：复制当时的 `system.txt` 为 `vN-日期-短名.txt`，在本表追加一行，不要改旧档。人工回归见 [evals/prompt/](../../../../../evals/prompt/README.md)。
