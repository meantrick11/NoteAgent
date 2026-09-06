# scripts

运维/调试脚本。只调用 `noteagent` 包，密钥只从环境变量读。

## 包含模块

| 文件 | 作用 |
|------|------|
| `index_notes.py` | 按篇重建 Chroma（与审批后的 `index_note` 相同；collection 损坏时用） |
| `sdk_smoke.py` | 用 `DEEPSEEK_API_KEY` ping 一次聊天 API |
| `eval_notes.py` | 离线提示词评测：进程内 `ChatAgent`，结果写入 `evals/prompt/results/<jsonl 主文件名>/` |

## 基础使用

索引一篇笔记（需已配置 embedding 缓存）：

```bash
uv run python scripts/index_notes.py Agent.md
# 成功会打印 indexed Agent.md: N chunks
uv run python scripts/index_notes.py --help
```

检查 DeepSeek 密钥是否可用：

```bash
uv run python scripts/sdk_smoke.py
# 未设置密钥时退出码 1
```

跑提示词黄金集（不启动 HTTP、不写用户 `notes/`、不人审）：

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03
# 结果在 evals/prompt/results/cases/<标签_>题号_时间/ ；未设置密钥时退出码 1
```
