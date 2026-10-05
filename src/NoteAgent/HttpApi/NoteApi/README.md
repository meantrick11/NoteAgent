# 笔记 HTTP

笔记和文件夹 CRUD、移动、索引操作。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/NoteApi/NoteRoutes.py](NoteRoutes.py) | 路由与接口注册 |
| [HttpApi/NoteApi/NoteSchemas.py](NoteSchemas.py) | 请求响应结构 |

## 主要接口

正式修改调用 NoteMutationService，NoteSchemas.py 定义 HTTP 契约。

## 依赖与约束

租约和运行快照来自公共依赖。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestNotesApi.py -q
```
