# 草稿审批流程

协调草稿校验、修改和发布；批准后通过 NoteMutationService 执行正式笔记修改。

## 文件职责

| 文件 | 职责 |
|---|---|
| [ApplicationFlows/DraftApproval/DraftApprovalWorkflow.py](DraftApprovalWorkflow.py) | 草稿审批与发布协调 |

## 接口

DraftApprovalWorkflow；ChatAgent 通过 DraftApproval 接口使用它，由 AppBootstrap 注入。

## 依赖与约束

依赖 ConversationState、NoteStorage、NoteRetrieval；不自行创建数据库连接，不处理 HTTP。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestCheckpointDraftApi.py -q`。
