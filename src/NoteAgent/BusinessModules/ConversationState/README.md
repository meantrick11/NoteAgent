# 会话状态

活动 checkpoint、消息投影、草稿状态、运行认领与租约。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/ConversationState/ConversationCheckpoints.py](ConversationCheckpoints.py) | checkpoint 存取 |
| [BusinessModules/ConversationState/ConversationContracts.py](ConversationContracts.py) | 调用契约和状态结构 |
| [BusinessModules/ConversationState/PendingDrafts.py](PendingDrafts.py) | 草稿数据与状态 |
| [BusinessModules/ConversationState/TurnLeases.py](TurnLeases.py) | 租约 |
| [BusinessModules/ConversationState/ConversationModels.py](ConversationModels.py) | ORM 或业务数据结构 |
| [BusinessModules/ConversationState/ConversationRecords.py](ConversationRecords.py) | 会话及消息记录 |
| [BusinessModules/ConversationState/TurnExecution.py](TurnExecution.py) | 运行准备、认领和结束 |
| [BusinessModules/ConversationState/ConversationStateService.py](ConversationStateService.py) | 模块主要接口 |
| [LegacyConversationCompatibility/](LegacyConversationCompatibility/README.md) | 旧会话存储、旧数据导入及兼容审批 |

## 主要接口

ConversationService 为主要接口；TurnExecution.py 为内部运行实现，复用同一事务辅助函数。

## 依赖与约束

使用共享 Base、checkpoint 和 NoteAccessControl 共享状态；LegacyConversationCompatibility 仍负责侧栏元数据和旧数据导入。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestConversationState.py Tests/Unit/TestTurnSafety.py Tests/Integration/TestTurnRecoveryPg.py -q
```
