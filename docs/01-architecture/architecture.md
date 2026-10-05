# NoteAgent 当前实现架构

当前会话执行与展示使用 LangGraph checkpoint；应用元数据维护明确活动 head。笔记正文由统一 mutation 服务记录影子 Git，RAG 按受影响文件维修。需求和架构决策见 [上层文档](../../../NoteAgent-docs/README.md)，本文件随代码版本更新。

## 模块与存储

| 分区 | 职责与代码 |
|---|---|
| bootstrap | app/runtime 装配、saver 生命周期、崩溃后维修 |
| conversations | checkpoint 状态、活动分支、revision、运行 claim、用户输入前 boundary |
| chat | 图执行、上下文压缩、草稿审批、工具/SSE 投影 |
| notes | repository 正文、versions 独立 bare Git、mutations 唯一正式写入口 |
| retrieval | chunker、Chroma、正文/配置指纹、持久 index repairs |
| recovery | workspace gate、纯 planner、持久 coordinator、HTTP |
| model_management | 运行对象与模型切换；先 workspace gate 再 runtime 锁 |
| frontend | Vue 页面、持久消息编辑/复制、预览确认、任务重试与续跑 |

PostgreSQL 应用表保存会话元数据与运行/恢复台账；AsyncPostgresSaver 保存 GraphState。notes_dir 保存正文，NOTES_HISTORY_DIR 默认 var/notes_history 保存材料字节历史，Chroma 是可重建派生索引。工程 .git 不承担笔记版本。多个状态可共享 notes_commit，没有文件变化不提交笔记版本。

## 一次聊天

POST /chat 校验版本并认领运行→保存输入前 boundary 与 user→从明确 checkpoint 运行图→节点状态持久保存→完成后发布活动 head。GET 消息从 active checkpoint 的 ui_messages 投影；模型使用 working_records、running_summary 和本轮 runtime_messages。压缩不删展示历史。租约过期的 running 标 interrupted，显式 run_id 续跑；已接受恢复消息的 prepared 不因等待超时丢失。

草稿保持 pending_draft；编辑只发布状态。批准经统一 mutation 写正文、Git 和按文件 RAG，随后发布清草稿状态。写正文时持久 approval maintenance，取消/崩溃后启动继续完成，避免重复写盘。未迁移 legacy 会话保持只读，禁止旁路审批。

## 整体恢复

用户编辑→纯预览→共享修改冲突拦截或文件/目录变更确认→独占门禁内重验会话、revision、seq、正文/目录及编辑摘要→job 与 maintenance 同事务认领→只撤销边界后的自有操作→维修全部受影响索引→保存隐藏候选和 prepared turn→CAS 原子发布 head/job/解除维护→用户显式或前端接续重新生成。

外来修改保留，不能整仓 reset。Git/saver/Chroma 没有统一事务；持久日志、幂等和最后发布保证可恢复。失败维持维护状态，任务查询与受控 retry 保留；刷新从 detail.recovery 找回失败任务。详见 [实现与故障处理](../03-modules/recovery/recovery.md)。

## 并发与可信检索

read/chat 用 shared gate；mutate/recovery/model_rebuild 用 exclusive gate。HTTP/SSE 响应完成才释放租约。writing 与 maintenance 同事务保存，worker 死亡释放 PostgreSQL advisory lock 后仍拒绝其他操作，直至补偿或完成 retained ref 发布。

IndexRepairService 先记 pending，再删旧向量并按当前正文重建，验证整文件字节哈希、配置指纹、完整片段内容/数量/偏移。只有 ready 且实时验证一致的片段可进入正式工具检索。启动扫描 failed/pending、正文与已有向量，修复缺失或删去孤儿路径。

## 验证入口

[执行结果](../05-records/plans/2026-10-04-checkpoint-shadow-git-completion-results.md) 包含 B1–B9 原执行与补验。Tests/Integration/TestRecoveryProcessDrills.py 使用真实 PostgreSQL/Git/Chroma 和真实子进程验证终止/重启及两进程竞争；frontend/Tests/E2e/checkpoint-edit-real.spec.ts 验证真实 HTTP 编辑确认、重生成与刷新。模型/embedding 在这些验收中使用确定性替身。

部署镜像安装 Git；Compose 独立 notes_history 卷保留材料历史。必须同时备份 notes、影子 Git 与 PostgreSQL，索引可从正文重建。详见 [部署指南](../04-ops/getting-started.md)、[数据库](database.md)、[上下文](../03-modules/chat/context-management.md)、[检索](../03-modules/retrieval/retrieval.md)。


## 源码组织

源码分为 HTTP、业务模块、跨模块流程、基础设施、装配五个入口，见 [源码导航](../../src/NoteAgent/README.md)。审批由 ApplicationFlows/DraftApproval 协调，模型运行由 ApplicationFlows/ModelRuntime 管理，恢复由 ApplicationFlows/ConversationRecovery 协调。笔记修改台账属于 BusinessModules/NoteStorage/ChangeJournal，恢复任务记录属于 BusinessModules/ConversationRecovery，共享访问状态属于 TechnicalSupport/NoteAccessControl，索引维修属于 BusinessModules/NoteRetrieval/IndexRepair，评测位于 Tools/noteagent_evals。HTTP、表名和磁盘数据格式不变。

## 上层模块命名与归属（2026-10-05）

当前后端按 HttpApi、BusinessModules、ApplicationFlows、TechnicalSupport、AppBootstrap 五个职责入口组织，自有 Python 包和文件采用大驼峰。原 workspace 拆为 NoteStorage/ChangeJournal、TechnicalSupport/NoteAccessControl、BusinessModules/ConversationRecovery。最新目录及旧名映射见 [源码导航](../../src/NoteAgent/README.md)。同一数据库事务可以调用多个模块的 ORM，包归属变化不改变提交边界。
