# V1 收尾修复与生成验收报告

本报告对应计划 [`docs/plans/2026-09-26-v1-acceptance.md`](../plans/2026-09-26-v1-acceptance.md)，记录写入异常修复、25 条生成验收样例集、自动测试与真实模型评测的实际结果。**手动功能验收由用户执行，本报告不代其判定。**

## 1. 范围与身份

| 项 | 值 |
|----|----|
| 日期 | 2026-09-26 |
| 执行者 | Qoder 执行代理（自动测试与内容审查均由代理执行，**不是**独立人工验收） |
| 分支 / 提交 | `feat/v1-acceptance` / `c8161ab`（任务 1、2 已提交；本轮评测产物在任务 3 提交中一并归档） |
| 未提交差异 | 仅用户既有改动：`docs/references/思考.md`（已修改）、`docs/references/亮点的地方.md`、`docs/roadmap/版本1.1代码解析.md`（未跟踪）。这三处与本次改动无关，未被改动或提交 |
| Python / 平台 | Python 3.13.5 / Windows 10.0.22635（win32, x64） |
| 运行模型 | `deepseek-v4-flash`（`CHAT_MODEL`），`deepseek_api_base=https://api.deepseek.com/` |
| Judge | 未配置 `JUDGE_MODEL`，本轮 `judge_model=disabled`，25 条均为 `task_mode=""`，不触发语义 Judge |
| system prompt | `src/noteagent/chat/prompts/system.txt`，SHA-256 `24d3623d9ee72d8ab4dfb202794ab8e3db5808689eb984e3e4642cba18cacc3f` |
| 样例 `v1_acceptance.jsonl` | SHA-256 `a29daece82be411c7700178789824ee088a303b65e5c5f1b854049c2fb680dd3` |
| 样例 `cases.jsonl` | SHA-256 `76bf7655991b6b594905e8b2f2e2c56bb0b37943f3a10997cd3487830709f1c5` |
| 修复文件 `drafts.py` | SHA-256 `26858f1ddd57eab619086ecf044fdaca5ac12cad08239b270851eea723b35d4e` |

CLI 使用 `Settings` 的模型配置（`.env`），**不保证等于界面已激活的 profile**。上表记录的是脚本实际运行使用的模型，不是 UI 显示的名称。

## 2. bug 修复：写盘异常导致待审草稿丢失

**原因。** `commit_review` 先执行 `store.pop(thread_id)`：该操作读取草稿后清空 `conversations.pending_draft`。随后 `_write_draft` 抛出的异常只捕获 `FileNotFoundError / FileExistsError / NotePathError / ValueError`。`PermissionError` 以及其它 `OSError` 会逃逸出函数，导致这次审批既没有写成文件，也把唯一一份待审草稿从数据库里抹掉。

**修改。** `src/noteagent/chat/drafts.py`：

- 捕获元组改为 `(OSError, ValueError)`。`FileNotFoundError`、`FileExistsError`、`PermissionError` 都是 `OSError` 子类，`NotePathError` 继承 `ValueError`，覆盖没有放宽到 `Exception`，程序性错误仍会抛出。
- 失败日志由 `thread / error` 扩展为 `thread / action / file / error`，便于定位是哪个目标文件写失败；不打印草稿正文。
- 失败路径先 `store.put(thread_id, draft)` 把草稿写回数据库，再返回 `{"error": ...}`。

**回归测试。** `tests/unit/test_drafts.py` 新增：

- `test_write_error_preserves_draft_and_allows_retry`（参数化 `PermissionError` / `OSError`）：写盘失败后断言 `DraftStore(store._history).get(tid)` 仍能从中读出完整草稿（重新包装同一个数据库，不是查局部变量）、文件内容未变、未索引、未删向量；恢复写盘后再次审批成功，且正文只追加一次。
- 五类操作边界：create 在创建前失败、replace 写入前失败、delete 删除前失败、override 写盘失败、create 已建标题后追加正文失败。均用 `monkeypatch` 注入异常，不改真实目录权限。
- `test_index_failure_keeps_written_file` 保持不变并继续通过：索引失败不是文件写盘失败，已写入的草稿**不**恢复成待审，避免重复写入。

**限制（不得写成"事务回滚成功"）。** 本修复只保证**写盘异常后草稿仍在数据库中**，不提供文件写入原子性：

| 场景 | 数据库草稿 | 文件系统 |
|------|-----------|----------|
| create 在 `notes.create` 前失败 | 完整保留 | 未创建目标文件，可直接重试 |
| create 已建标题、追加正文失败 | 完整保留 | **残留 `# 标题` 文件**，重试同名 create 会 `FileExistsError`，需人工核对后处理 |
| replace / append 写入前失败 | 完整保留 | 原文不变，可直接重试 |
| replace / append 写入中途失败 | 完整保留 | 可能部分写入，需人工核对文件 |
| delete 删除前失败 | 完整保留 | 文件仍在，可直接重试 |

本轮不扩展为文件事务改造（计划明令排除）。

## 3. 自动测试

全部在 `feat/v1-acceptance` / `c8161ab` 上运行，原始记录保存在本地 `var/v1-acceptance/`（该目录按 `.gitignore` 为运行时数据，不入库）：

| # | 命令 | 退出码 | 结果 | 原始记录 |
|---|------|--------|------|----------|
| 1 | `python -m pytest tests/unit/test_drafts.py tests/unit/test_chat_history.py tests/integration/test_retrieval_service.py -q` | 0 | 61 passed in 10.67s | `var/v1-acceptance/pytest-group1.txt` |
| 2 | `python -m pytest tests/unit/test_v1_acceptance_cases.py tests/unit/test_prompt_eval_run.py tests/unit/test_prompt_eval_score.py -q` | 0 | 32 passed in 10.80s | `var/v1-acceptance/pytest-group2.txt` |
| 3 | `python -m pytest tests -q` | 0 | 478 passed, 1 warning in 35.07s | `var/v1-acceptance/pytest-all.txt` |

- 跳过数 0，失败数 0。
- 唯一 warning 是第三方 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`，与本次改动无关。
- 未遇到临时目录权限导致的 fixture 初始化失败，不需要改 `--basetemp`；未出现需要区分环境错误与产品断言失败的情况。
- 本次改动引入的回归：无。任务 1 与任务 2 的测试在首次运行时按预期失败（先红后绿），实现后全绿。

## 4. 样例覆盖

| 集合 | 条数 | 是否计入本轮生成验收 |
|------|------|----------------------|
| `evals/prompt/v1_acceptance.jsonl`（g01–g25） | 25 | 是，分母固定 25 |
| `evals/prompt/cases.jsonl`（n01–n13 / b01–b07） | 20 | 否，行为/正文回归，单独记账 |
| `evals/prompt/learning_notes.jsonl`（l01） | 1 | 否，v0.2 加工质量单独记账 |

新增 g 集的口径：

- 五类各 5 条：dialogue（g01–g05）、long_text（g06–g10）、english（g11–g15）、code（g16–g20）、modify（g21–g25）。
- 每条 `kind=quality`、`expect_propose=true`、`expect_action ∈ {create, append, replace}`，必须产生非空正文；寒暄、拒答、只检索、删除与固定候选评分不计入这 25 条（删除仍由 `b06` 回归）。
- 长文类材料长度（字符数，仅覆盖检查，不是质量分）：g06 2433、g07 2362、g08 2041、g09 2250、g10 2156。
- modify 类提供完整 `seed_files`；三条 replace 的 `expect_tools_prefix` 是 `["list_files", "read_file"]`（对应系统提示词"先 list_files 再 read_file 读全文"的契约），两条 append 是 `["list_files"]`，避免给每条设同一工具顺序。
- 完整性由 `tests/unit/test_v1_acceptance_cases.py` 自动检查：条数、ID 集合、分类计数、`user` 互不相同、字段取值、长文长度、modify 必须有 seeds、`load_cases()` 可加载 25 条（无需改加载器或 CLI）。
- 逐条语义断言写在 [`evals/prompt/v1_acceptance.md`](../../evals/prompt/v1_acceptance.md)。其中只有 `must_anchors` 与 `must_headings` 会被 L1 打分器自动检查，其余（禁止添加事实、代码/路径约束、合理改写边界）由内容审查对照执行，报告不伪称它们已被脚本校验。

## 5. 25 条明细

运行：`v1-acceptance-full_all_20260926-095957`（2026-09-26 09:59:57–10:03:23，`deepseek-v4-flash`，`judge_model=disabled`）。逐条结论由**执行代理内容审查**给出，不是独立人工验收；结果链接指向该次运行的逐条报告。

| ID | 分类 | 动作（预期/实际） | 目标文件 | 正文 | 审查依据与结论 |
|----|------|-------------------|----------|------|----------------|
| [g01](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g01.md) | dialogue | create / create | 项目周会记录.md | 320 | 四项分工与两个日期齐全；"登录改版收尾"如实标为「由王磊布置、会上未明确执行人」，未编造负责人。通过 |
| [g02](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g02.md) | dialogue | create / create | 数据库索引.md | 273 | 定义、例子（一千万行订单表按用户号建索引）、限制（写入维护成本、低选择性字段）齐全。通过；锚点 `小林` 未命中（见 §6.2） |
| [g03](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g03.md) | dialogue | create / create | 缓存层选型-Redis与本地内存.md | 352 | 「讨论中提出的方案」与「最终决定」分节，理由（会话需跨实例读）与回退条件都在。通过；锚点 `周航`、`许晨` 未命中 |
| [g04](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g04.md) | dialogue | create / create | 502故障排查记录.md | 314 | 六步按顺序保留，`upstream timed out`、30 秒→5 秒都在；「重启 Nginx 没用」单独成节，未被写成解决方案。通过 |
| [g05](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g05.md) | dialogue | create / create | 上线时间安排.md | 197 | 最终结论为 10 月 12 日凌晨两点；9 月 28 日、10 月 8 日标为不采用并给出原因；10 月 11 日预发布与负责人苏晴保留。通过；锚点 `唐维` 未命中 |
| [g06](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g06.md) | long_text | create / create | SQLite WAL.md | 2580 | 11 节齐全；`PRAGMA journal_mode=WAL;`、`wal_checkpoint(TRUNCATE)` 在围栏内原文保留；"WAL 改变并发行为而非查询速度"的限定保留。通过 |
| [g07](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g07.md) | long_text | create / create | API服务部署手册.md | 2613 | 13 节齐全；第 5 节恢复的适用条件（配置结构未变才可只回退软链接，否则连配置一起还原）完整保留。通过 |
| [g08](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g08.md) | long_text | create / create | 幂等性.md | 2071 | 13 节齐全；幂等与重试的前提关系、不解决并发覆盖、不可逆副作用边界都在，无来源外结论。通过 |
| [g09](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g09.md) | long_text | create / create | 定时任务方案对比.md | 2288 | 三种方案与五个比较维度齐全，选择建议保留"按规模选型"的原意而非单一正解。通过 |
| [g10](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g10.md) | long_text | create / create | DatabaseMigration.md | 2168 | 三条备注与三处例外全部以 `>` 引用保留；`通常/一般/建议/默认` 未被改成绝对说法。通过 |
| [g11](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g11.md) | english | create / create | 服务账号与网关调用约定.md | 296 | may / must / usually 强度差别保留（"可以随时读取"/"必须在每个请求的 Authorization 头发送"/"通常在五分钟后过期"）；三个标识符原样。通过（L1 命中 `faithful.hedge`，见 §6.1） |
| [g12](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g12.md) | english | create / create | PythonHTTP服务器.md | 428 | `python -m http.server 8000`、`--directory ./site`、`netstat -ano \| findstr :8000`、`Ctrl+C` 原样且在围栏内。通过 |
| [g13](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g13.md) | english | create / create | CSP-nonce.md | 387 | `nonce`、`Content-Security-Policy`、`strict-dynamic`、`unsafe-inline` 未翻译改名；"每个响应重新生成"与"两者并存时退回允许内联"两条限制保留。通过 |
| [g14](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g14.md) | english | create / create | gzip-zstd-brotli 对比.md | 317 | 12 MB→2.4 MB/1.1 s、zstd 2.1 MB/0.4 s、brotli 2.2 MB/0.7 s、100 MB 9.5 s/2.8 s、"不到 8%" 全部与输入一致。通过 |
| [g15](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g15.md) | english | create / create | SearchIndexIncident.md | 312 | 现象、根因、临时处置、后续修复四节分开；`503`、`alias`、`Retry-After`、40% 保留。通过 |
| [g16](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g16.md) | code | create / create | ExponentialBackoff.md | 528 | 函数体与 `>>>` 三段返回值 `0.5 / 4.0 / 30` 正确，围栏语言标注与缩进正确。通过 |
| [g17](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g17.md) | code | create / create | SQL订单查询.md | 842 | 六个字段、`WHERE` 三条件、`ORDER BY created_at DESC`、`LIMIT 20` 全在；占位符与"排序不要用 id"的注意事项保留。通过 |
| [g18](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g18.md) | code | create / create | PowerShell清理旧日志.md | 744 | 三条命令的参数、单引号路径 `'D:\backup'`、`-WhatIf` 原样；`-WhatIf` 版保留为预演步骤，未被写成直接删除的生产命令。通过 |
| [g19](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g19.md) | code | create / create | APIClientConfig.md | 579 | 六个键与取值齐全（含占位符 `REPLACE-WITH-YOUR-KEY`）；`max_retries=3` 表示最多 4 次请求的说明保留；未编造真实密钥。通过 |
| [g20](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g20.md) | code | create / create | Python可变默认参数.md | 551 | 错误版被显式标注"不要使用"并说明共享列表的错因，修正版正确；未把错误写法当作推荐实现。通过 |
| [g21](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g21.md) | modify | append / append | Go.md | 192 | 只追加「切片」一节；原「控制流」一节未改动；备注以 `>` 呈现；未改用 replace。通过 |
| [g22](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g22.md) | modify | replace / replace | Python虚拟环境.md | 272 | 路径不变；「适用版本」更新为 3.10 及以上；「创建」「常见问题」原文保留；含一级标题。通过 |
| [g23](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g23.md) | modify | append / append | Kafka.md | 100 | 目标文件是 `Kafka.md`，**没有**写进 `RabbitMQ.md`；「分区」一节原文保留。通过 |
| [g24](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g24.md) | modify | replace / replace | 网络/HTTP缓存.md | 230 | 路径不变；「协商缓存」补全为 `ETag`/`If-None-Match`/304 与 `Last-Modified` 版本；「强缓存」一句原文保留。通过 |
| [g25](../../evals/prompt/results/v1_acceptance/v1-acceptance-full_all_20260926-095957/g25.md) | modify | replace / replace | Python/工具函数.md | 243 | 路径不变；签名改为含 `max_delay=None`；「缓存」一节与 `@lru_cache(maxsize=32)` 原样保留。通过 |

代码类与命令类的围栏检查：g12、g16、g17、g18、g19、g20、g25 的草稿都包含围栏且语言标注正确（材料含代码态时才要求围栏）。

## 6. 分组汇总

| 分组 | 通过 / 条数 | 运行错误 |
|------|-------------|----------|
| dialogue | 5 / 5 | 0 |
| long_text | 5 / 5 | 0 |
| english | 5 / 5 | 0 |
| code | 5 / 5 | 0 |
| modify | 5 / 5 | 0 |
| **全量** | **25 / 25** | **0** |

分母固定 25，未因任何失败剔除样例。行为门 25/25（动作与 `expect_action` 全部一致），正文非空 25/25，`must_headings` 全部命中。

L1 总分（**仅作辅助**，不代替内容审查）：最低 62.25、最高 100.0、平均 85.56、中位 82.28。分类上 modify 与 long_text 偏高（93.76–100.0），dialogue / english / code 集中在 73.34–83.7，差异主要由 §6.1 的 `structure.heading_precision` 偏差造成，而不是正文质量差异。

### 6.1 自动评分命中已知偏差

| 指标 | 命中条目 | 实际表现 | 处理 |
|------|----------|----------|------|
| `faithful.hedge` | g11 | 草稿忠实译出 `must` → `必须`，被判为"情态加强"，`faithful` 父项 50.0 | 内容判据为准（必须与 may 的区别正是本条要求），偏差记录不改期望 |
| `structure.heading_precision` | dialogue 5 条、english 5 条、code 5 条（共 15 条） | 材料没有原标题，草稿新增的语义子标题被逐条判为"发明标题"→ 该指标 0，`structure` 父项固定 40.0 | 系统提示词明确允许"增加有正文依据的子标题"，此偏差属打分器口径；未改打分器（计划未授权） |
| `structure.heading_precision` | g22、g25 | replace 材料的用户输入未重复一级标题，草稿必须保留的 H1 被判"发明"→ 5 分 | 同上 |
| `form.list` | g01、g04 = 0；g03、g05、g14、g17 = 5 | 对话与步骤类整理成列表，列表行占比 > 50% 判 0 | 内容无误；计划已预告该偏差 |
| `retrievable.file_name_topic` | g05、g07、g09、g10、g11、g12、g15、g16、g17、g18、g19、g20、g21、g22、g24、g25 = 5 | 文件名不含锚点字面量（多为英文文件名或通用词） | 内容无误；文件名在合法范围内 |

`complete.compression` 本轮 25 条全部为 10，未命中。

### 6.2 锚点未命中的三条

| ID | 未命中锚点 | 事实判断 |
|----|-----------|----------|
| g02 | `小林` | 草稿按主题重组，未保留提问者姓名；定义/例子/限制三项关键事实齐全 |
| g03 | `周航`、`许晨` | 草稿按"方案—决定"重组，未保留发言人姓名；决定与理由齐全 |
| g05 | `唐维` | 草稿保留了苏晴，未保留提问者；最终日期与作废原因齐全 |

这三条的关键事实没有遗漏，未判为内容失败。**问题在我给的锚点**：对"整理成笔记"的对话材料，把每位发言人姓名设为自动断言过严——只有 g01 明确要求保留归属。已按实际情况记录，不回头修改锚点来制造满分；下一轮要么在输入里明确要求保留发言人，要么把这类锚点只写进审查清单。

## 7. 旧集回归

运行：`v1-acceptance-regression_all_20260926-100340`，`cases.jsonl` 20 条，`deepseek-v4-flash`。

| 项 | 本轮 | 上一轮对照（`rag-v10_all_20260925-132224`） |
|----|------|------------------------------------------|
| 模型 / prompt SHA / 样例 SHA | `deepseek-v4-flash` / `25fbb8a9…` / `76bf7655…` | 与左列完全相同 |
| 行为门 | 19 / 20 | 19 / 20 |
| b05 | **失败**（见 §8） | 通过 |
| n03 | 通过 | 失败 |
| L1 总分波动 | n04 100.0 → 81.72、n12 83.7 → 100.0、b02 91.85 → 100.0、n01 87.23 → 92.66 | 同左 |

- 两次运行使用同一模型与同一 prompt/样例哈希，因此差异只能来自采样；本轮没有任何"提示词或打分器改动"。
- **不改动被修改的产品代码路径**：本轮 `src/noteagent/chat/drafts.py` 的改动只在人审落盘路径（`commit_review`）上，评测脚本从不调用 `commit_review`，索引调用也由 `_FakeRetrieval` 替身承接。因此评测结果与本次修复无关。
- 单项 L1 总分在两次运行间可相差 20 分上下，**不参与任何"通过/未通过"判断**，也不据此宣布质量提升或下降。
- 正文回归（L1 正文分）与行为回归分别记录：行为门见上表；正文分仅作噪声观测，不设门槛。

## 8. 失败与复跑

| 失败 | 首次结果 | 分类 | 原因 | 复跑 | 是否解决 | 剩余风险 |
|------|----------|------|------|------|----------|----------|
| b05 | `v1-acceptance-regression_all_20260926-100340`，行为门失败 | 动作错误（未提案） | 该次运行里模型读完原文后，回复中声称"已按你的更正提交覆盖审批"并写出"提案：action=replace"，但**没有调用 `propose_note`**；`actual_tools` 停在 `read_file` | `v1-acceptance-b05-r1_b05_20260926-100921`（通过，`replace`，86.09）、`v1-acceptance-b05-r2_b05_20260926-100938`（通过，`replace`，84.11） | 判定为不稳定样例：3 次中 2 次通过；不是本次代码改动引入 | 模型在冲突提示分支下偶尔"只说明不提案"，并可能宣称已提案；属于提示词/工具调用稳定性的既有风险，本轮不修 |
| n03 | 上一轮 `rag-v10_all_20260925-132224` 行为门失败 | 动作错误 | 上一轮未通过；本轮通过 | `v1-acceptance-n03-r1_n03_20260926-100954`（通过，98.86） | 旧失败，本轮已复现为通过 | 同类波动风险 |
| g 集 | 无 | — | 25 条全部通过行为门且正文非空 | 未复跑 | — | — |

首次全量结果均已保留，复跑使用独立 run ID，未覆盖首次结果，也未按最好结果替换分母。

## 9. 手动功能验收（用户执行，已反馈通过）

以下项目**由用户执行**，执行代理不代跑。用户于 2026-09-26 反馈 V1 阶段已完成，本表据此记为"用户已验收"；**执行代理未逐项采集证据**（会话记录、截图），如需留档请另行补充。

| # | 场景 | 操作 | 期望 | 状态 |
|---|------|------|------|------|
| 1 | 创建后跨会话检索 | 新建会话记一条新笔记并审批通过，再开另一个会话提问该主题 | 能检索到刚写入的笔记，引用可溯源 | 用户已验收 |
| 2 | 追加 | 对已有笔记提出追加内容并审批 | 原文保留，新内容进入文件末尾 | 用户已验收 |
| 3 | 覆盖 | 对已有笔记提出更正并审批（replace） | 过时内容被替换，一级标题与其他章节保留 | 用户已验收 |
| 4 | 删除 | 对某篇笔记提出删除并审批 | 文件被删除，向量同步移除 | 用户已验收 |
| 5 | 拒绝 | 提出提案后点拒绝 | 文件不变，不产生索引变更 | 用户已验收 |
| 6 | 重启恢复 | 保留一份未审批草稿后重启服务，重新打开该会话 | 历史消息与待审草稿卡片都能恢复 | 用户已验收 |
| 7 | 写盘失败 | 让目标文件不可写（例如占用或只读目录）后审批 | 返回错误，文件未变，**待审草稿仍在**，恢复可写后可再次审批成功 | 用户已验收 |

第 7 项对应本轮修复；自动测试已用注入异常覆盖，真实文件系统上的表现由用户确认。

## 10. 结论

- **bug 修复**：完成后端写盘异常时保留待审草稿，捕获范围扩到 `(OSError, ValueError)`；6 类操作边界有确定性回归测试；`test_index_failure_keeps_written_file` 语义未回归。**限制**：不提供文件写入原子性，create 部分写入会残留标题文件，重试需人工核对（见 §2）。
- **自动测试**：三组命令退出码均为 0，全量 478 passed，无失败与跳过，未发现本次改动引入的回归。
- **生成验收**：25 条行为门与内容审查均通过，运行错误 0，分母 25 未被剔除；3 条锚点未命中已如实记录（§6.2）。**生成验收集本身的通过结论成立**，但不代表生成质量已优化——L1 偏差与单次采样波动见 §6.1、§7。
- **手动功能验收**：用户执行并反馈通过（§9，未逐项留证）。
- **V1 结论**：V1 退出标准已满足——核心闭环有可重复自动测试、生成样例 25 条覆盖五类、RAG 查询集 40 条（[rag-v1-report.md](./rag-v1-report.md)）、输入到审批到后续检索经用户手动确认。据此 **V1 验收通过，发布里程碑 tag `v1.0.0`**（路线图同步为已验收）。
- **遗留项（不阻塞 V1，进入 V2 或后续任务）**：① 旧集 `b05` 为不稳定样例，模型在冲突分支下可能"只说明不提案"并宣称已提案；② L1 的 `structure.heading_precision`、`faithful.hedge`、`form.list`、`file_name_topic` 偏差未修（计划未授权改打分器）；③ 对话类锚点设计过严，下一轮需调整输入或只放进审查清单；④ 手动验收无逐项证据留档。
