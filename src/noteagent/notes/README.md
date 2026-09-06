# notes（代码包）

对数据目录（默认仓库根 `notes/`）做确定性 Markdown IO，并拦住路径逃逸。embedding 与 LLM 不在本包。Documents 的 HTTP 在 `router.py`，不经过 Agent。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `repository.py` | `FileNoteRepository` | `list_notes` / `list_folders` / `create_folder` / `rename_folder` / `delete_folder` / `move` / `mtime` / `read` / `create` / `write` / `delete` / `exists` / `normalize` |
| `repository.py` | `NotePathError` | 空名、绝对路径、`..`、两层以上目录 |
| `router.py` | Documents HTTP | `GET/POST/PUT/DELETE /notes`、`POST /notes/{path}/index`、`POST /notes/folders`、`POST /notes/folders/rename`、`DELETE /notes/folders/{name}`、`POST /notes/move` |
| `schemas.py` | 请求/响应体 | 列表含 `mtime`、`indexed`（来自磁盘与 Chroma，无笔记表） |
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
repo.delete("Go.md")
```

`write` 默认追加；`append=False` 为覆盖。文件必须已存在。相对路径可以是 `Go.md` 或一层 `Python/GIL.md`。`read("../x.md")` 与 `read("a/b/x.md")` 会抛 `NotePathError`。Documents 页面的 HTTP 契约见 [frontend.md](../../../docs/architecture/frontend.md) §5。

```bash
uv run pytest tests/unit/test_note_repository.py -q
```
