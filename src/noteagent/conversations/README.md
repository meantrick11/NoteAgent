# conversations

## 执行安全与模块边界

- `contracts.py`：共享状态视图、prepared turn 句柄及 busy／stale／重复请求错误；旧 `service.py` 导入路径继续兼容。
- `leases.py`：数据库运行租约与过期处理；60 秒租期，图执行每 10 秒续租。跨 worker 不使用进程内锁保护会话。
- `service.py`：状态读写、运行认领、用户消息与安全边界原子接受、明确 head／generation CAS 发布。
- `chat/execution.py`：图执行、节点 checkpoint 指针、显式中断续跑和流资源关闭；不以 saver latest 推断活动状态。

每个会话至多一个 prepared／running／interrupted 运行，由数据库部分唯一索引兜底。用户状态、边界和已接受 checkpoint 在同一事务内发布；checkpoint 候选写入失败或边界失败，不显示未接受的消息，允许同一 request_id 重试。

`accepted_checkpoint_id` 是本轮接受用户消息时的应用 head，`checkpoint_id` 是运行过程中最新的明确节点位置，两者不可混用。恢复原执行只能在 accepted head、branch 和 generation 均未改变时进行，并重新取得 lease token；旧 token 不能发布或修改新执行者的运行状态。

进程退出后，启动或后续认领／续跑会检查已过期租约：未接受的 prepared 占位回收，已接受的 running 标记 interrupted，保留明确执行位置。不自动调用模型；60 秒内仍有效的租约不会被另一个 worker 回收。续跑入口目前是服务接口，正式 HTTP 切换仍属后续迁移任务。

数据库新增 revision `c8f31a024e76`。升级前必须结束或核对旧版本活动运行；迁移发现旧 prepared／running／interrupted 记录会在 DDL 前拒绝升级，不删除消息，也不推断旧状态位置。迁移已在临时 PostgreSQL schema 中验证，未对实际应用数据库执行。


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
