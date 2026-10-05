# 会话恢复记录

保存恢复预览、计划、任务阶段和执行状态。

## 文件职责

| 文件 | 职责 |
|---|---|
| [BusinessModules/ConversationRecovery/RecoveryModels.py](RecoveryModels.py) | 本包负责的 ORM 记录 |

## 接口

RecoveryPreview、RecoveryJob：仅提供 ORM 记录。恢复算法和执行流程位于 ApplicationFlows/ConversationRecovery。

## 依赖与约束

依赖 DatabaseAccess；会话发布时可在同一事务内更新恢复任务与共享维护状态。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestRecoveryCoordinator.py -q`。
