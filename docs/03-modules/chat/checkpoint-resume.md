# Checkpoint 会话续接与草稿并发

正式聊天经 `BusinessModules/ConversationState/ConversationStateService.py` 保存 checkpoint 状态，页面从活跃 head 投影消息和待审草稿。旧消息表不是正式聊天的新状态写入源。运行 claim 和会话 revision 是业务数据库中的协调信息；checkpoint 与业务数据库之间仍需要发布 head 来确定可见状态。

## 中断续接

会话详情包含 `active_run`。过期运行租约会协调为 `interrupted`，页面显示“继续生成”。点击后 `POST /chat` 携带 `conversation_id`、`run_id`、`expected_revision`，不携带 `question`。服务先校验所属会话、版本、运行状态和 checkpoint 边界，再认领运行。页面刷新不会自动调用模型；运行期间不能发送新问题。续接完成后从正式 checkpoint 重载消息，避免展示仅剩余流式片段。

## 草稿审批

新建草稿的笔记名可点击面板顶部编辑，Enter 或失焦提交本地更名，Esc 取消；保存草稿或审批前的自动保存将正文和文件名一起写入 checkpoint，未批准前不写 notes。底部直接提供同意、拒绝、追加到笔记；追加需选择目标并确认。PUT /chat/draft 可带 file_name（仅 create），路径由笔记仓库规范化，仍按 expected_revision 发布并拒绝运行占用。

每个会话面板保存自己正在编辑的草稿及 `draftRevision`。本地未保存正文不会因为详情刷新、会话切换或 draft SSE 获得更新后的版本；过期保存／审批返回冲突，保留本地正文。异步响应只更新发起请求的会话。

审批在同一 Conversation 行锁下检查运行占用和版本，读取固定 head，保存未发布的清草稿候选，然后执行正文写入和 head 发布。新回合认领、续接及 head 发布均遵循该锁。被拒绝的审批以及 saver 候选写入失败不会触碰正文。重命名／删除的同步数据库调用在工作线程运行，以免审批等待 saver 时阻塞事件循环。

## 材料写入与恢复边界

影子 Git、持久 mutation、按文件索引维修与消息编辑已经接入。writing 与 maintenance 同事务，草稿 applied 同时保留 approval maintenance，清草稿发布将日志置 published 并解除维护。取消/重启由启动流程完成同一操作，避免正文已写而状态未清的不一致。

恢复后的 prepared run 持久保留直到显式领取，不被 60 秒未接受输入的临时 claim 清理。POST /chat 在认领前验证所属会话和 revision；刷新后可继续生成。详细操作见 [恢复模块](../recovery/recovery.md)，验证见 [执行结果](../../05-records/plans/2026-10-04-checkpoint-shadow-git-completion-results.md)。
