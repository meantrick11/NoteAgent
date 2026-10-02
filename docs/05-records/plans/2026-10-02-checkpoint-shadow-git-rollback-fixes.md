# Checkpoint 回退迁移验收问题修复记录

日期：2026-10-02。起点：`92b0086`。依据：[实施 plan](2026-10-01-checkpoint-shadow-git-rollback.md) 与 [验收记录](2026-10-02-checkpoint-shadow-git-rollback-review.md)。修改留在当前工作区，保留原有文档迁移和 `main.py` 改动。

## 本轮修复完成情况

- [x] 会话运行认领使用 PostgreSQL 行锁与数据库部分唯一索引；不同 request_id 不能同时接受到同一会话。
- [x] head 发布校验 branch、expected checkpoint 和 generation，过期发布不能覆盖新状态。
- [x] checkpoint 先写成未发布候选，再将用户 head、消息边界及 running 状态一起提交；saver 或边界失败后可使用原 request_id 重试，不丢失／重复显示用户。
- [x] 提案工具在节点私有草稿工作区执行，将 pending_draft 随 tools 节点立即持久化；finalize 从 checkpoint 读取草稿。历史草稿不再被旧表覆盖。
- [x] 图运行使用 prepared turn 中明确的 checkpoint，通过框架 checkpoints 流记录每个持久节点的位置；测试夹具不再使用 saver latest，也不再把失败统一标为 completed。
- [x] 完成时在同一事务内 CAS 发布 head 和终态；lease token 条件更新防止旧执行者覆盖新的续跑占位。
- [x] 提供显式中断续跑，保留工具消息和 pending_draft，不重复加入用户消息；也覆盖接受消息后、图尚未开始的退出窗口。
- [x] 使用数据库 60 秒运行租约、10 秒心跳；过期未接受的 prepared 回收，过期 running 标记 interrupted；不自动重跑模型，不回收其他 worker 的有效租约。
- [x] 两层异步流均显式关闭，等待图／模型任务清理后才释放运行占位。
- [x] 摘要节点支持异步摘要回调，原同步回调放到工作线程，避免阻塞事件循环；压缩仍保留完整显示历史。
- [x] 模块拆分为 `conversations/contracts.py`、`conversations/leases.py` 与 `chat/execution.py`，会话持久化和图执行分别承担职责。
- [x] 新增 Alembic revision `c8f31a024e76`，验证 PostgreSQL 升级／降级；旧版本活动 run 坐标无法可靠推断时在 DDL 前明确拒绝迁移，不删除已有记录。
- [x] 修复完整回归暴露的原有模型重建门禁竞争：任务终态与门禁释放在同一锁内发布；旧 worker 退出不能释放新重建任务的门禁。两项原有并发测试补上实际待索引文件，避免空语料跳过阻塞点。

## 测试证据

先观察新增用例失败，再实施修复。覆盖并发接受、saver／边界故障重试、迟到 head 发布、草稿恢复、工具之后中断、模型任务关闭、未启动图的续跑、候选状态隔离、异步摘要、过期占位、真实 PostgreSQL 重开及跨服务认领。

独立代码复核发现的进一步竞争条件也已转成测试：在 PostgreSQL 完成提交前让另一个服务过期回收并续跑，旧实现会覆盖新 token；修复后旧提交被 CAS 拒绝。旧版本活动 run 的迁移保护也已按失败→修复→通过验证。

最终完整后端回归命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --basetemp var/qoder-review-2026-10-02/fix-complete-tmp -o cache_dir=var/qoder-review-2026-10-02/fix-cache --tb=short
```

最终结果：**552 passed，1 warning，36.49 秒**。最初完整回归暴露的模型重建终态／门禁竞争和空语料并发测试夹具问题均已修复，并补充成功、失败、旧 worker 退出期间新重建任务的确定性验证。警告仍是现有 Starlette/httpx 依赖弃用提示。真实 PostgreSQL 测试在隔离临时 schema 中运行，未升级实际应用数据库。独立复核在会话修复和新增门禁修复范围内没有剩余 P1／P2 发现。

框架 checkpoint 事件模式核对依据：[LangGraph StreamMode 官方参考](https://reference.langchain.com/python/langgraph/types/StreamMode)，同时核对了本项目安装版本的执行循环源码；显式 `durability="sync"` 后才把节点位置记入运行元数据。

## 原计划的剩余范围

本记录完成的是验收缺陷修复和图核心恢复安全补齐，**不表示整体迁移完成**。正式 ChatAgent／HTTP／评测切换、旧会话导入、前端消息 ID／复制，以及阶段 B 的统一文件写入、影子 Git、逐文件 RAG 修复、编辑弹窗／冲突拦截和部署验收仍需按原 Task 2～12 继续实施。当前不会开放半迁移的编辑入口，也未对用户 notes 做任何回撤。

正式数据库升级遇到旧活动 run 时，应先备份并停止旧 worker，再核对原 head、运行节点与消息边界，完成或明确终止原运行后重试迁移；不得直接删除记录以绕过保护。
