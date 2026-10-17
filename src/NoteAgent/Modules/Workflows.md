# 跨模块流程

跨模块流程留在发起它的业务模块中，不另设全局 `ApplicationFlows` 目录。

- 草稿审批：`Chat/Service/DraftApprovalWorkflow.py` 协调 Conversations 的草稿状态与 Notes 的正式写入。
- 模型切换：`Models/Service/ModelRuntime.py` 协调配置、运行快照和 Retrieval 索引。
- 会话恢复：`Recovery/Service/` 协调 Conversations、Notes 和 Retrieval。

这些流程通过各模块明确的入口调用，不直接复用对方的 HTTP Router。
