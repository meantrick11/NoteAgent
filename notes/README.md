# notes（数据目录）

正式知识的 Markdown。这是数据，不是 Python 包，不要放 `.py`。本 README 不参与向量索引。

代码侧对应 [`src/noteagent/notes`](../src/noteagent/notes/README.md) 的 `FileNoteRepository`，根路径由 `NOTES_DIR` 决定（默认就是本目录）。

## 包含内容

| 文件 | 说明 |
|------|------|
| 主题 `.md`（如 `Agent.md`） | 已审批的学习笔记 |
| `context.md` | MVP 会话摘要/近况，不是主题知识，后续可能拆掉 |
| `README.md` | 本说明，索引脚本不要索引它 |

## 基础使用

- 日常由聊天审批通过后写入，不要手改文件名成带空格或子目录。
- 文件名用主题：`Go.md`、`Backtracking.md`。
- 写入后若要语义检索：

```bash
uv run python scripts/index_notes.py Backtracking.md
```
