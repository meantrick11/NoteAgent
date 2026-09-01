# evals

LLM / Agent / RAG 的黄金集与人工评分说明。产物写 `var/eval/`（不入库）。不要把私人笔记全文放进来。

**不要放进 `tests/`。** `tests/` 是无网络、无真实 LLM 的 pytest。本目录不进默认 CI。不要让写草稿的同一个模型给自己打分。

| 目录 | 用途 |
|------|------|
| [prompt/](prompt/README.md) | 系统提示 + 记笔记质量 + 意图门（第一期 13 条） |
| [rag/](rag/README.md) | 检索 query（尚未填） |
| [agent/](agent/README.md) | 多 hop 轨迹（尚未填；能复用 prompt 集则先复用） |

## 笔记质量（六条）

星级：★★★★★ / ★★★★ 任一失败则该条笔记不合格。流畅/形态/可检索不单独用来决定「这版 prompt 能不能留下」，但要勾。

| 条 | 星 | 核心问题 |
|----|----|----------|
| 忠实 | ★★★★★ | 有没有幻觉/篡改？ |
| 完整 | ★★★★★ | 有没有漏东西？（相对任务：提纲/只要某节时少写不算漏） |
| 结构 | ★★★★ | 组织是否符合材料本身？ |
| 流畅 | ★★★ | 整理之后能不能正常读？ |
| 形态合适 | ★★★ | 有没有为了「像 AI 笔记」套模板？代码/命令/备注是否用了围栏或 `>`？ |
| 可检索 | ★★ | 以后还能不能找到？标题锚点优先算完整，文件名算可检索，不要同一处扣两次硬门 |

## 人工怎么打这 13 条

把 [`prompt/cases.jsonl`](prompt/cases.jsonl) 的 `user` 贴进聊天（改提示词后请重启进程）。看气泡、工具轨迹（日志）和草稿卡片。

每条先过 **行为门**，再过笔记六条（仅 `expect_propose=true` 时评正文）：

1. 是否调用了 `propose_note`，是否与 `expect_propose` 一致。该提案时，`list_files` 是否出现在 `propose_note` 之前（见 `expect_tools_prefix`）。
2. 草稿 `content` 是否包含全部 `must_headings`（原文含编号）；是否出现 `forbidden_headings`。
3. 是否包含全部 `must_anchors`。
4. `content` 是否以 `# ` 当正文一级标题（不合格）。
5. `style` 为 `faithful_paragraphs` 时，主体应是段落，不是口号短要点；`outline` 允许短列表；`excerpt` 不应出现未点名的其它大节标题。材料里有代码/命令/REPL/备注时，草稿须有围栏 ` ``` ` 或 `>` 引用，否则**形态合适不过**（n03 另见 `must_substrings`）。
6. 人勾忠实/完整/结构（过/不过）与流畅/形态/可检索（过/不过或 0–2）。

失败则记下 id，只改一类 prompt，归档 `prompts/iterations/vN`，再跑同一 13 条。

## 字段

`id`、`kind`（quality|behavior）、`user`、`expect_propose`、`expect_tools_prefix`、`must_headings`、`forbidden_headings`、`must_anchors`、`must_substrings`（可选）、`style`。
