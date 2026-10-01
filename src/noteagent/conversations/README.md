# conversations

会话元数据、活动分支指针与 checkpoint 状态的读写。**不**包含 HTTP、恢复流程或 LLM 调用。

| 文件 | 职责 |
|---|---|
| `records.py` | 纯记录类型：`MessageRecord`/`ConversationRecord` 与持久化的 `GraphState` schema；不含 Session |
| `models.py` | `conversation_branches` / `conversation_runs` / `user_message_boundaries` ORM，`Base` 来自 `db` |
| `checkpoints.py` | `CheckpointRuntime` 异步生命周期与 config 适配（线程 id、固定 namespace、显式 checkpoint_id） |
| `service.py` | `ConversationService`：创建会话、活动 head 查询、状态读写与 head 发布 |

关键约束：

- LangGraph 自身的 checkpoint 表由 saver 的 `setup()` 管理，本模块不手写仿 checkpoint 表。
- 所有读取/更新都传**明确 checkpoint_id**；saverse 的“最新 checkpoint”不代表活动分支。
- 逻辑 `branch_id` 与 head config 由应用元数据（本模块的表）管理，框架 fork 不替应用选择活动分支。
