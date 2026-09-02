# notes（数据目录）

正式知识的 Markdown。这是数据，不是 Python 包，不要放 `.py`。本 README 不参与向量索引。

代码侧对应 [`src/noteagent/notes`](../src/noteagent/notes/README.md) 的 `FileNoteRepository`，根路径由 `NOTES_DIR` 决定（默认就是本目录）。

## 包含内容

| 文件 | 说明 |
|------|------|
| 主题 `.md`（如 `Agent.md`） | 已审批的学习笔记 |
| `context.md` | 历史遗留文件，**不再**作为聊天记忆写入；主题知识仍在各笔记 `.md` |
| `README.md` | 本说明，索引脚本不要索引它 |

## 基础使用

- 日常由聊天审批通过后写入并自动索引。不要手改文件名成带空格或子目录。
- 文件名用主题：`Go.md`、`Backtracking.md`。
- 向量库损坏时可用脚本按篇重建：

```bash
uv run python scripts/index_notes.py Backtracking.md
```
