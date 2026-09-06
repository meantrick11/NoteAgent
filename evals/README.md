# evals

本目录放**黄金集（考题）**和提示词离线跑分结果。不要把私人笔记全文放进来。

**准则不在这里。** 记笔记正文怎么打分、六条和小指标、与生成链路的隔离：见 [docs/evaluations/](../docs/evaluations/README.md)，尤其是 [note-quality.md](../docs/evaluations/note-quality.md)。

**不要放进 `tests/`。** `tests/` 是无网络、无真实 LLM 的 pytest。本目录的一键脚本不进默认 CI。不要让写草稿的同一个模型给自己打分。不要往 `notes/` 回流生成结果。

| 目录 | 用途 |
|------|------|
| [prompt/](prompt/README.md) | 系统提示 / 笔记正文考题（20 条）+ 意图门 behavior 条；结果在 [prompt/results/](prompt/results/README.md) |
| [rag/](rag/README.md) | 检索 query（尚未填） |
| [agent/](agent/README.md) | 多 hop 轨迹（尚未单开；能复用 prompt 集则先复用） |

## 怎么跑

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03 --prompt src/noteagent/chat/prompts/system.txt
```

进程内 `ChatAgent`（`CHAT_MODEL` + 四工具），临时 notes / SQLite，不启动 HTTP，不人审写盘。无 `DEEPSEEK_API_KEY` 时退出码 1。

每条先过 **行为门**，再评笔记正文（仅实际提案时评 `content`）：

1. 是否调用了 `propose_note`，是否与 `expect_propose` 一致。该提案时，`list_files` 是否出现在 `propose_note` 之前（见 `expect_tools_prefix`）。
2. 草稿 `content` 是否包含全部 `must_headings`（原文含编号）；是否出现 `forbidden_headings`。
3. 是否包含全部 `must_anchors`。
4. `content` 是否以 `# ` 当正文一级标题（结构扣分）。
5. `style` 为 `faithful_paragraphs` 时，主体应是段落；`outline` 允许短列表；`excerpt` 不应出现未点名的其它大节标题。材料里有代码/命令/REPL/备注时，草稿须有围栏或 `>` 引用（n03 / n08 另见 `must_substrings`）。

行为失败与正文分两列记，不混成一个 Agent 总分。失败则记下 id，只改一类 prompt，归档 `prompts/iterations/vN`，再跑同一集。

## 字段

`id`、`kind`（quality|behavior）、`user`、`expect_propose`、`expect_tools_prefix`、`must_headings`、`forbidden_headings`、`must_anchors`、`must_substrings`（可选）、`style`、`expect_action`（可选）、`seed_files`（可选，评测开始前写入临时 notes）。
