# 跨模块业务流程

协调多个业务能力，执行审批、模型切换和会话恢复。

## 子模块职责

| 模块 | 职责 |
|---|---|
| [DraftApproval/](DraftApproval/README.md) | 草稿审批与正式笔记修改协调 |
| [ModelRuntime/](ModelRuntime/README.md) | 模型切换、运行快照、租约及索引重建协调 |
| [ConversationRecovery/](ConversationRecovery/README.md) | 恢复规划、任务执行和重试 |

## 接口与依赖

调用 BusinessModules 和共享技术能力，不导入 HTTP。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestFullRollbackAcceptance.py -q`。
