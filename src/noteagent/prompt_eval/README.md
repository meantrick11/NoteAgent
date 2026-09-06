# prompt_eval

离线提示词评测：读黄金集、进程内跑 `ChatAgent`、按 v0.1 L1 打分、写 `evals/prompt/results/<jsonl 主文件名>/`。

**chat 不得 import 本包。** 不 `commit_review`，不写用户 `NOTES_DIR`。

## 包含模块

| 文件 | 作用 |
|------|------|
| `cases.py` | 读 `evals/prompt/cases.jsonl` |
| `score.py` | 行为门 + L1 小指标；L2 摊权；失败不评正文 |
| `report.py` | `{id}.md` / `index.json` / `config.json` |
| `run.py` | 临时 notes + sqlite，装配与线上同构的四工具 Agent |

入口：[scripts/eval_notes.py](../../../scripts/eval_notes.py)。准则：[docs/evaluations/note-quality.md](../../../docs/evaluations/note-quality.md)。

## 基础使用

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03 --prompt src/noteagent/chat/prompts/system.txt
```

未设置 `DEEPSEEK_API_KEY` 时退出码 1。同一结果目录已存在时拒绝覆盖，除非 `--force`。不进默认 CI。
