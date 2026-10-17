# Chat

`Router/` 提供聊天与草稿审核接口；`Domain/Dto/` 保存 HTTP 对象，`Domain/Vo/` 保存聊天事件；`Service/` 协调草稿审批。`Agent/Graph/` 执行图与节点，`Agent/Context/` 管理上下文，`Agent/Tools/` 放聊天工具，`Agent/SystemPrompts/` 保存当前提示词。会话状态由 Conversations 持有，正式笔记写入由 Notes 持有。
