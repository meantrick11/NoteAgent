# 恢复流程

持久预览、冲突分析、文件恢复、索引维修、候选状态和原子发布。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [ApplicationFlows/ConversationRecovery/RecoveryCoordinator.py](RecoveryCoordinator.py) | 恢复状态机 |
| [ApplicationFlows/ConversationRecovery/RecoveryPlanner.py](RecoveryPlanner.py) | 恢复范围与冲突 |

## 主要接口

RecoveryCoordinator.preview/start/retry，RecoveryPlanner.py 计算恢复范围。

## 依赖与约束

调用 ConversationState、NoteStorage、NoteRetrieval 与 NoteAccessControl。任务记录位于 BusinessModules/ConversationRecovery/RecoveryModels.py，HTTP 入口为 HttpApi/ConversationRecoveryApi。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestRecoveryPlanner.py Tests/Integration/TestRecoveryCoordinator.py Tests/Integration/TestRecoveryProcessDrills.py -q
```
