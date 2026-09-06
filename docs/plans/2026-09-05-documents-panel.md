# Documents 面板（一层目录 + 编辑保存同步向量）

> 实现规格。Chat 仍是默认首页。不新建笔记元数据表。

**Goal:** 顶栏 Chat | Documents。Documents 可按一层真实目录分类、打开编辑、保存后按相对路径整篇重索引。Agent 的 `file_name` 与磁盘相对路径一致。

**Architecture:** `FileNoteRepository` 允许 `Folder/Note.md`（禁止两层与 `..`）。Documents HTTP 直写磁盘后调用现有 `index_note` / `delete_note`。用户点保存即人审，不走 `propose_note`。mtime 来自文件 `stat`；是否可检索看 Chroma 该 `file_name` 有没有点。

**Tech Stack:** FastAPI、`home.html`、Chroma、`FileNoteRepository`。

## Global Constraints

- 默认落地 Chat（`GET /`）；`GET /documents` 同一模板切视图。
- 只一层目录：`notes/Python/GIL.md`。根下 `notes/*.md` 为未分类。
- 不新建 PG 笔记表、不加 YAML、不做 Dashboard、不做嵌套树、不做勾选入库、Agent 不提供 mkdir。
- 写盘成功后按该相对路径删旧向量再整篇索引；索引失败不回滚 Markdown。

---

## 文件

| 文件 | 改动 |
|------|------|
| [`notes/repository.py`](../../src/noteagent/notes/repository.py) | 一层路径；`list_folders` / `create_folder` / `move` / `mtime` |
| [`notes/router.py`](../../src/noteagent/notes/router.py)（新） | `GET/PUT/DELETE /notes`、mkdir、move |
| [`notes/schemas.py`](../../src/noteagent/notes/schemas.py)（新） | 列表/正文/move 请求体 |
| [`bootstrap/app.py`](../../src/noteagent/bootstrap/app.py) | `include_router(notes_router)` |
| [`chat/router.py`](../../src/noteagent/chat/router.py) | `GET /documents` 下发同一 `home.html` |
| [`retrieval/vector_store.py`](../../src/noteagent/retrieval/vector_store.py) | `has_file_name` |
| [`retrieval/service.py`](../../src/noteagent/retrieval/service.py) | `is_indexed` |
| [`chat/tools.py`](../../src/noteagent/chat/tools.py)、[`drafts.py`](../../src/noteagent/chat/drafts.py)、[`system.txt`](../../src/noteagent/chat/prompts/system.txt) | 相对路径；create 标题用 stem |
| [`web/templates/home.html`](../../src/noteagent/web/templates/home.html) | 顶栏 + Documents 左树右编辑器 |

## 验收

- 一层路径合法；两层与 `../` 拒绝。
- PUT 保存后假 embedding 下 search 命中新正文；move 后旧路径无向量。
- `list_files` 含 `Folder/a.md` 与文件夹名。
- `GET /` 仍是 Chat；页面有 Documents 入口。

## 不做

Dashboard、嵌套目录、页内勾选入库、PDF、Agent mkdir、笔记状态表。
