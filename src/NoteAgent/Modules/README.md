# 业务模块

| 模块 | 职责 |
|---|---|
| [Conversations/](Conversations/README.md) | 会话、消息、草稿状态与 checkpoint |
| [Chat/](Chat/README.md) | Agent 执行、上下文、工具和草稿审批 |
| [Notes/](Notes/README.md) | 正式笔记、文件夹、版本和修改台账 |
| [Retrieval/](Retrieval/README.md) | 切块、检索、索引及维修 |
| [Models/](Models/README.md) | 模型配置、探测与运行对象 |
| [Sources/](Sources/README.md) | 上传文件、解析、片段和原文件存储 |
| [Recovery/](Recovery/README.md) | 跨会话、笔记和索引的恢复流程 |

模块内按 `Router/`、`Domain/Dto|Vo|Po/`、`Service/`、`Mapper/` 归属代码；文件、向量库、模型客户端和解析器使用对应模块的专属目录。只建立当前确实需要的目录。
