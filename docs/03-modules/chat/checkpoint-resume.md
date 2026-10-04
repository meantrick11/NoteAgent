# Checkpoint 会话续接与草稿并发

正式聊天经 `conversations/service.py` 保存 checkpoint 状态，页面从活跃 head 投影消息和待审草稿。旧消息表不是正式聊天的新状态写入源。运行 claim 和会话 revision 是业务数据库中的协调信息；checkpoint 与业务数据库之间仍需要发布 head 来确定可见状态。

## 中断续接

会话详情包含 `active_run`。过期运行租约会协调为 `interrupted`，页面显示“继续生成”。点击后 `POST /chat` 携带 `conversation_id`、`run_id`、`expected_revision`，不携带 `question`。服务先校验所属会话、版本、运行状态和 checkpoint 边界，再认领运行。页面刷新不会自动调用模型；运行期间不能发送新问题。续接完成后从正式 checkpoint 重载消息，避免展示仅剩余流式片段。

## 草稿审批

每个会话面板保存自己正在编辑的草稿及 `draftRevision`。本地未保存正文不会因为详情刷新、会话切换或 draft SSE 获得更新后的版本；过期保存／审批返回冲突，保留本地正文。异步响应只更新发起请求的会话。

审批在同一 Conversation 行锁下检查运行占用和版本，读取固定 head，保存未发布的清草稿候选，然后执行正文写入和 head 发布。新回合认领、续接及 head 发布均遵循该锁。被拒绝的审批以及 saver 候选写入失败不会触碰正文。重命名／删除的同步数据库调用在工作线程运行，以免审批等待 saver 时阻塞事件循环。

## 当前边界

成功审批仍通过原索引同步流程更新 RAG。影子 Git、持久文件 mutation、崩溃补偿、按文件索引维修及用户消息编辑回退属于后续 B 阶段；当前没有整体回退保证。正文已写入而最终数据库提交失败的场景仍需该阶段处理。

验证和实施范围见 [阶段 A 修复记录](../../05-records/plans/2026-10-04-checkpoint-shadow-git-completion-fixes.md)。
