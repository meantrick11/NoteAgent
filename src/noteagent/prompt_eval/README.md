# prompt_eval

离线提示词评测：读黄金集、进程内跑 `ChatAgent`、执行确定性检查与可选语义 Judge、写 `evals/prompt/results/<jsonl 主文件名>/`。

**chat 不得 import 本包。** 不 `commit_review`，不写用户 `NOTES_DIR`。

## 包含模块

| 文件 | 作用 |
|------|------|
| `cases.py` | 读 `evals/prompt/cases.jsonl` |
| `score.py` | 旧 case 的 v0.1 分数 + 学习型笔记硬门和维度资格判定 |
| `judge.py` | 独立调用语义 Judge，严格校验 JSON 结果 |
| `report.py` | `{id}.md` / `index.json` / `config.json` |
| `run.py` | 临时 notes + sqlite，装配与线上同构的四工具 Agent |

入口：[scripts/eval_notes.py](../../../scripts/eval_notes.py)。准则：[docs/evaluations/note-quality.md](../../../docs/evaluations/note-quality.md)。

## 基础使用

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03 --prompt src/noteagent/chat/prompts/system.txt
python scripts/eval_notes.py --judge --cases evals/prompt/learning_notes.jsonl --ids l01
```

`--judge` 要求 `JUDGE_MODEL` 非空；模型名可与 `CHAT_MODEL` 相同，但此时配置会记录 `judge_independent=false`。不传 `--judge` 时保持旧流程，学习型 case 明确显示“语义评测未完成”，不生成语义总分。Judge 响应缺字段、分数越界或不是严格 JSON 时记入 `judge_failures`，不会静默补默认值。

未设置 `DEEPSEEK_API_KEY` 时退出码 1。同一结果目录已存在时拒绝覆盖，除非 `--force`。Judge 不发送用户笔记库，只评当前 case 来源和草稿；日志不记录密钥或整篇正文。该校准集只有一个 Python 教程样本，不能证明对其他教程泛化，也不进默认 CI。
