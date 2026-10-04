# 整体恢复实现与故障处理

代码分区：`recovery/` 负责门禁、预览、协调与 HTTP；`notes/` 负责正文 mutation 和影子 Git；`retrieval/repairs.py` 负责索引维修；`conversations/` 负责候选状态和活动指针。上层契约见 [REQ-018](../../../../NoteAgent-docs/docs/02-requirements/REQ-018-历史消息编辑与整体回退.md)。

## 材料写入

生产 Library 和 checkpoint 草稿批准走 NoteMutationService。独占门禁内初始化真实材料版本、识别外部修改、读取前像和 expected hashes，再同事务记 writing/maintenance。写盘和 Git 完成后，台账、workspace seq/current_commit 一起发布；Git 失败完整恢复字节和目录，包括 CREATE/MOVE/目录重命名产生的文件。Git 已提交但数据库未发布时从 retained operation ref 完成，不重复 append。

审批写盘成功后保持 approval maintenance，直到清草稿 checkpoint 发布与 mutation published 一起提交。取消或崩溃后启动补完审批；未迁移 legacy 会话不可旁路写盘。

默认 NOTES_HISTORY_DIR 为 `var/notes_history`，独立 bare Git；目录 manifest 保存空目录，目录路径以 `/` 结尾标记。初始版本在首次写入前保存；普通聊天不创建材料版本，多 checkpoint 可引用同一 notes_commit。

## 编辑与恢复协议

1. 消息必须有真实输入前 boundary；预览只读，绑定会话、revision、seq、编辑摘要、文件和目录摘要、15 分钟有效期。
2. 只撤销边界后的本会话操作。其他会话、Library、外部修改触碰受影响路径即冲突，整次拒绝；无强制覆盖入口。
3. 有文件/目录变化必须确认全部路径；取消不启动恢复。start 在独占门禁内重验，再同事务创建任务和 maintenance。
4. 逐路径补偿当前树，保留他人不相关新内容，不能整仓 reset。移动/重命名恢复文件、附件和目录。
5. 按受影响 Markdown 文件删除旧向量并重建，验证正文哈希、当前配置及完整片段内容/数量/偏移。失败保持 maintenance，不发布成功。
6. 恢复输入前摘要、压缩记录、草稿，保存隐藏候选及单次 edited user，创建 prepared run。候选保存后重试复用身份。
7. CAS 事务发布活动 head、任务成功与解除维护；成功后通过 prepared_turn_id 显式生成。prepared 可持久等待，运行中断则 run_id 续跑。

HTTP start 当前同步执行，成功返回 200 JobOut；错误时任务可能已持久保存。GET 会话详情的 recovery 找回任务；GET /recoveries/{job_id} 与 POST retry 在维护期间可用。前端切换会话丢弃迟到结果，刷新失败任务仍显示重试入口。

## 并发与重启

read/chat shared，mutate/recovery/model_rebuild exclusive；租约覆盖 HTTP/SSE 生命周期。worker 死亡释放 advisory lock 后，持久维护记录继续封锁。启动处理 writing 的 retained ref 或前像补偿、approval 发布与索引 reconcile；恢复任务保持原计划并等待受控 retry。

备份 PostgreSQL 应用/saver、notes 和影子 Git；Chroma 可按正文重建。Docker 镜像需要 Git，Compose 独立 notes_history 卷。丢失 Git 历史不能用最新 notes 重造历史能力。

## 验证

真实 PostgreSQL/Git/Chroma worker 终止重启和双进程竞争：`tests/integration/test_recovery_process_drills.py`。真实 HTTP 编辑→确认→恢复→生成→刷新：`frontend/tests/e2e/checkpoint-edit-real.spec.ts`。故障矩阵见 [补验结果](../../05-records/plans/2026-10-04-checkpoint-shadow-git-completion-results.md)。模型与 embedding 在这些测试中为确定性替身；本轮未运行 Docker 镜像构建。
