# scripts

运维/调试脚本。只调用 `noteagent` 包，密钥只从环境变量读。

## 包含模块

| 文件 | 作用 |
|------|------|
| `index_notes.py` | 把 `NOTES_DIR` 下指定 Markdown 切块写入 Chroma |
| `sdk_smoke.py` | 用 `DEEPSEEK_API_KEY` ping 一次聊天 API |

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
