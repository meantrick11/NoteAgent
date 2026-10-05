# 业务能力

按业务对象聚合实现和持久化，不接收 HTTP 请求。

## 子模块职责

| 模块 | 职责 |
|---|---|
| [ChatAgent/](ChatAgent/README.md) | 执行 Agent 图、工具和上下文处理 |
| [ConversationState/](ConversationState/README.md) | 会话、执行轮次、草稿和 checkpoint 状态 |
| [NoteStorage/](NoteStorage/README.md) | Markdown 读写、正式修改、版本和台账 |
| [NoteRetrieval/](NoteRetrieval/README.md) | 检索、索引与维修 |
| [ModelSettings/](ModelSettings/README.md) | 模型配置、凭据、客户端及探测 |
| [ConversationRecovery/](ConversationRecovery/README.md) | 恢复预览和任务数据 |

## 接口与依赖

公开业务接口由各子包说明；持久化记录随业务归属。

## 验证

从仓库根运行：`uv run pytest Tests/Unit/TestSourceOrganization.py -q`。
