# var

运行时派生数据：日志、可选缓存。整目录删掉后可以重建（README 除外）。不要把 `var/` 下内容提交进 git。

## 包含模块

| 路径 | 作用 |
|------|------|
| `logs/noteagent.log` | 默认日志（`LOG_DIR`） |
| `models/` | Settings 默认 embedding 缓存相对路径（若你没用绝对 `EMBEDDING_CACHE_DIR`） |

Chroma 默认仍在仓库根 `chromadb_persist/`，兼容已有索引。可设 `CHROMA_DIR=var/chroma` 改到这里。

## 基础使用

启动后看日志：

```text
var/logs/noteagent.log
```

排查 Agent：搜 `LLM start`、`Tool start`、`context pack`、`compact`、`draft pending`、`draft committed`。磁盘满了可删 `noteagent.log` 或整个 `logs/`，下次启动会再建。
