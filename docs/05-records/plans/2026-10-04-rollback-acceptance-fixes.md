# 整体回退验收修复计划

Goal：修复阶段 B 验收的 15 项缺陷，补齐 G12/G14/G16，按原批准方案交付可实际使用的消息编辑回退。

Architecture：工作区门禁先于 runtime 和会话锁；持久 mutation 记录完整前像并原子发布台账与 seq；恢复计划在独占门禁内重验，文件和索引成功之后才发布 checkpoint。候选、用户消息边界、prepared run 使用一致身份，所有阶段可幂等续办。

Tech Stack：Python/FastAPI/SQLAlchemy/PostgreSQL/LangGraph/Git/Chroma/Vue。

Spec：[原完成计划](2026-10-04-checkpoint-shadow-git-completion.md)、[B 验收报告](2026-10-04-checkpoint-shadow-git-completion-review-b.md)。沿用已批准的冲突拦截、文件变更确认和双仓文档规则。不合并、不推送，不改个人笔记。

## 批次 1：持久写入（S-B03/04/05/08）

- [x] 在 `test_notes_mutations.py` 先加入 Git 失败 CREATE/MOVE/目录重命名精确撤销、writing 台账重试不重复 append、锁内 hash 校验用例，运行确认失败。
- [x] `notes/mutations.py` 锁内读取／验证，记录包含不存在与目录的前像，复用 retained ref，原子推进 seq 与台账；失败补偿不吞异常。
- [x] `bootstrap/app.py`、`notes/router.py` 和 `chat/agent.py` 区分生产历史不可用与测试兼容，生产拒写。
- [x] 运行 mutation/API/草稿回归并提交。

## 批次 2：恢复协调（R-B01/02/03/05/06/07、S-B06）

- [x] `test_recovery_coordinator.py` 先加入 preview 后 Library 写入保留、index failed 阻断、各 fault stage 重试、prepared run 可完成／中断续接、保留压缩与草稿用例，确认失败。
- [x] `recovery/service.py` 锁内重新验证身份／seq/hash／冲突，持久 maintenance 和固定计划；复用已保存候选；索引严格验证后发布。
- [x] `conversations/service.py` 统一恢复用户消息 ID、边界及 generation，幂等 fork、发布和 claim；`recovery/router.py` 副作用前校验所属会话。
- [x] 运行 coordinator/API/full acceptance/PG recovery 回归并提交。

## 批次 3：正式门禁、检索与编辑能力（S-B01/02、R-B04）

- [x] 加入正式 HTTP maintenance 阻断、工具检索过滤、启动维修以及消息 editable 用例，确认失败。
- [x] 接通 runtime 门禁，避免嵌套锁和异步响应提前释放；接通 index repair 的过滤／启动和显式维修；根据可恢复边界开放消息编辑。
- [x] 使用真实 HTTP 后端验证编辑→预览→确认→恢复→重新生成→刷新，再提交。

## 批次 4：前端会话隔离（S-B07）

- [x] 在 `message-recovery.spec.ts` 加预览／轮询／确认期间切换会话、旧响应、失败重试用例，确认失败。
- [x] `store.ts` 为恢复请求绑定 owner 和 token，准备回合始终使用 job owner，选择切换不污染新会话。
- [x] 单测、E2E、构建通过后提交。

## 批次 5：现场演练与文档（G12/G14/G16）

- [x] 临时真实 PG schema、笔记、影子 Git、向量目录，用独立进程做持久恢复终止／重启及双进程竞争，保留结果；不使用用户 notes。
- [x] 同步 `NoteAgent-docs` 的需求／架构／模块／数据／接口／质量／追溯与变更记录；仅本地 Git 记录。
- [x] 复跑全部后端／前端／浏览器／构建，按 G01—G16 更新真实结果，独立代码复核后提交。

每批执行红→绿测试，结果记录到本计划的结果文档；必要的分区仅服务于上述修复，不做额外架构替换。

## 执行结果

批次修复统一验证后提交 ea6bb8c，上层文档 eb59aa5；详见 [结果](2026-10-04-checkpoint-shadow-git-completion-results.md) 补验章节。后端 646 passed/1 skipped、前端143 单测/61 E2E/build、真实终止重启与双进程竞争均通过。Docker 静态校验，未构建运行。不合并、不推送。
