# 共享笔记资源访问控制

协调聊天和读取、笔记修改、历史恢复、索引重建对共享笔记资源的访问。

## 文件职责

| 文件 | 职责 |
|---|---|
| [TechnicalSupport/NoteAccessControl/NoteAccessGate.py](NoteAccessGate.py) | 共享/独占访问锁与维护控制 |
| [TechnicalSupport/NoteAccessControl/NoteAccessModels.py](NoteAccessModels.py) | 本包负责的 ORM 记录 |

## 接口

WorkspaceGate：共享/独占访问和维护状态；WorkspaceState：修改序号、当前版本、维护任务记录。

## 依赖与约束

依赖 DatabaseAccess。PostgreSQL 使用跨进程 advisory lock，进程退出释放锁；维护记录持久化保留。底层 Workspace 类名和数据库标识本轮保留。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestWorkspaceGatePg.py Tests/Integration/TestRecoveryProcessDrills.py -q`。
