# 提示词评测：数据集 + 一键脚本

> 不改聊天人审链路，不按分数再生成。准则：[../evaluations/note-quality.md](../evaluations/note-quality.md)。

**Goal:** `uv run python scripts/eval_notes.py --name v8-baseline` 在进程内跑与线上同构的 `ChatAgent`（含工具），按 v0.1 打分，结果写入 `evals/prompt/results/<阶段>/`。

**不启动** FastAPI / 浏览器。不写用户 `NOTES_DIR`。不 `commit_review`。不进默认 CI。

## 跑法

考题是人写的输入，不是「生成合格再当答案」。脚本读 [`evals/prompt/cases.jsonl`](../../evals/prompt/cases.jsonl)，临时 notes + SQLite，调用真实 `CHAT_MODEL`，收集工具与草稿，L1 打分。L2（矛盾/流畅等）本期不适用并摊权。

## 结果目录

```text
evals/prompt/results/<阶段名>/
  config.json    # rubric、模型、prompt hash、时间、题号与 md 文件名
  system.txt     # 本阶段提示词全文
  index.json     # 各题总分目录（差的在前）；不能替代 md
  01.md          # 第 1 题完整记录
  02.md
```

`01.md` 固定小节：题头、得分摘要、小指标表、行为、输入（含 seed_files）、工具轨迹、草稿、助手气泡。不写本机 notes 绝对路径、密钥、token 流。

## 文件

| 路径 | 职责 |
|------|------|
| `evals/prompt/cases.jsonl` | 考题 |
| `src/noteagent/prompt_eval/` | 打分 / 渲染 / 跑 case；chat 不得 import |
| `scripts/eval_notes.py` | CLI |
| `ChatAgent.prompt_path` | 可选，默认仍读现行 system.txt |

## 任务

1. 扩充黄金集（n07–n13、b04–b06 的 `seed_files`）
2. L1 `score_note` + 无网络单测
3. 渲染 `01.md` / `index.json` / `config.json`
4. 临时 Agent + `scripts/eval_notes.py`
5. README：evals、docs/evaluations、scripts

## 明确不做

不改 `propose_note` / 人审 / 前端；不把结果写入 `notes/`；不做 L2 Judge 与 RAG 评测集。
