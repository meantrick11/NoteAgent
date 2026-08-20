# notes（代码包）

对数据目录（默认仓库根 `notes/`）做确定性 Markdown IO，并拦住路径逃逸。不做 embedding、HTTP、LLM。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `repository.py` | `FileNoteRepository` | `list_notes` / `read` / `create` / `write` / `exists` |
| `repository.py` | `NotePathError` | 空名、绝对路径、`..`、子目录 |
| `__init__.py` | 再导出 | `from noteagent.notes import FileNoteRepository` |

## 基础使用

```python
from pathlib import Path
from noteagent.notes.repository import FileNoteRepository

repo = FileNoteRepository(Path("notes"))
repo.create("Go.md", "Go")           # 写入 "# Go\n\n"
repo.write("Go.md", "## 循环\n- 只有 for\n\n", append=True)
print(repo.read("Go.md"))
print(repo.list_notes())
print(repo.exists("Go.md"))
```

`write` 默认追加；`append=False` 为覆盖。文件必须已存在。`read("../x.md")` 会抛 `NotePathError`。

```bash
uv run pytest tests/unit/test_note_repository.py -q
```
