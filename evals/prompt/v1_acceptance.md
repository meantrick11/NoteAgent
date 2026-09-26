# v1 生成验收样例集（g01–g25）

本文件是 [`v1_acceptance.jsonl`](./v1_acceptance.jsonl) 的逐条验收口径。JSONL 是考题，本文件写清每条要保留什么、禁止添什么、怎么算失败。**本文件里的语义断言目前由人工/执行代理逐条对照审查，不由脚本自动校验**；JSONL 的 `must_anchors`、`must_headings` 会由 `scripts/eval_notes.py` 的 L1 打分器自动检查，`must_substrings` 与 `must_preserve` 仅供审查时对照。

## 定位与账本

| 集合 | 作用 | 是否计入本集 |
|------|------|--------------|
| `v1_acceptance.jsonl`（g01–g25） | V1 生成覆盖验收：每条都必须产生非空笔记正文 | 是，25 条 |
| `cases.jsonl`（n01–n13 正文 / b01–b07 行为） | 旧行为集与旧正文集，作为行为/正文回归 | 否，单独记账 |
| `learning_notes.jsonl`（l01） | v0.2 学习型笔记校准集 | 否，单独记账 |

- 25 条固定为五类各 5 条：dialogue、long_text、english、code、modify。
- 每条 `kind=quality`、`expect_propose=true`、`expect_action` 只能是 `create` / `append` / `replace`，必须产生非空正文。
- 寒暄、拒答、只检索、删除、固定候选评分**不算**这 25 条，删除仍由 `b06` 单独回归。
- 长文类每条的 `user` 不少于 2,000 个字符；长度只是覆盖检查，不作为质量分数。

## 运行方式

```bash
uv run python scripts/eval_notes.py --cases evals/prompt/v1_acceptance.jsonl --name v1-acceptance-full
uv run python scripts/eval_notes.py --cases evals/prompt/cases.jsonl --name v1-acceptance-regression
```

无密钥时脚本退出码 1，不会写入结果目录。结果落在 `evals/prompt/results/v1_acceptance/` 与 `evals/prompt/results/cases/` 下，**不要用 `--force` 覆盖首次结果**。

## 判据

单条判通过需要同时满足：

1. 产生了草稿，且 `content` 非空、不是只有标题；
2. 动作与目标文件符合下表（`expect_action` 由 L1 行为门自动检查，目标文件由审查确认）；
3. 必须保留的事实均在文中，且没有来源外的关键结论；
4. 代码、命令、标识符、路径符合输入要求，未被改写或损坏；
5. 未把来源中的错误示例当作推荐实现。

L1 的 `total` 只作辅助。没有执行语义 Judge 时，不得把 `semantic_completed=false` 写成语义通过，也不得用 `total` 代替内容审查。

## 分类总表

| ID | 预期动作 | 目标文件（合理范围） | 必须保留（自动锚点） | 禁止添加 / 主要风险 |
|----|----------|----------------------|----------------------|---------------------|
| g01 | create | 项目周会相关，如 `项目周会.md` / `周会纪要.md` | `王磊`、`李静`、`周会` | 不得把任务负责人张冠李戴；不得补出对话里没有的日期或任务 |
| g02 | create | 索引相关，如 `数据库索引.md` / `索引.md` | `小林`、`索引`、`订单` | 不得只留“索引像目录”一句结论；不得补出材料没有的索引类型 |
| g03 | create | 缓存选型相关，如 `缓存选型.md` / `Redis.md` | `周航`、`许晨`、`Redis` | 不得把讨论中提到的两个方案都写成已决定；不得添加材料外的结论 |
| g04 | create | 故障复盘相关，如 `502故障排查.md` / `连接池故障.md` | `502`、`Nginx`、`连接池` | 不得把“重启 Nginx”写成有效步骤；不得打乱排查先后顺序 |
| g05 | create | 上线计划相关，如 `上线时间.md` / `发布计划.md` | `唐维`、`苏晴`、`预发布` | 不得把作废的 `9 月 28 日` 或 `10 月 8 日` 写成最终结论 |
| g06 | create | WAL 相关，如 `SQLite WAL.md` / `WAL 模式.md` | `WAL`、`PRAGMA`、`wal_checkpoint` | 不得漏 `PRAGMA journal_mode=WAL;`；不得把 WAL 说成提升查询速度 |
| g07 | create | 部署手册相关，如 `API 部署.md` / `服务部署手册.md` | `systemd`、`api-run`、`healthz` | 不得省略第 5 节恢复的适用条件；不得添加材料外的部署步骤 |
| g08 | create | 幂等相关，如 `幂等.md` / `幂等设计.md` | `幂等键`、`重试`、`幂等` | 不得加材料外的结论；不得把幂等说成解决并发覆盖 |
| g09 | create | 定时任务相关，如 `定时任务方案.md` / `定时任务对比.md` | `cron`、`systemd timer`、`队列调度` | 三种方案都要在；不得漏比较维度；不得把方案三写成唯一正解 |
| g10 | create | 数据库迁移相关，如 `数据库迁移流程.md` / `迁移流程.md` | `回填`、`迁移`、`回滚` | 备注/例外/条件不得丢；限定语不得改成绝对说法 |
| g11 | create | 接口调用约束相关，如 `接口调用约束.md` / `网关规则.md` | `Authorization`、`Cache-Control`、`401` | may / must / usually 的强度差别不得抹平；不得把 may 写成必须 |
| g12 | create | 本地静态服务相关，如 `本地静态服务.md` / `http.server.md` | `http.server`、`--directory`、`netstat` | 命令与选项保持原样；不得改写端口、不得省略 `--directory` |
| g13 | create | CSP 相关，如 `CSP nonce.md` / `内容安全策略.md` | `nonce`、`Content-Security-Policy`、`strict-dynamic`、`unsafe-inline` | 标识符不得翻译或改写；不得添加材料外的绕过手法 |
| g14 | create | 压缩对比相关，如 `压缩算法对比.md` / `gzip对比.md` | `gzip`、`zstd`、`brotli`、`0.4` | 数值不得改动；不得把某一项说成所有场景最优 |
| g15 | create | 故障复盘相关，如 `搜索503复盘.md` / `索引别名故障.md` | `503`、`Retry-After`、`alias` | 原因、现象、workaround 不得混为一谈；不得把 workaround 写成根因修复 |
| g16 | create | 退避函数相关，如 `指数退避.md` / `retry_delay.md` | `retry_delay`、`max_delay`、`0.5` | 围栏、缩进、返回值须正确；`>>>` 示例不得丢失；不得把返回值写错 |
| g17 | create | 订单查询相关，如 `订单查询.md` / `orders 查询.md` | `orders`、`created_at`、`LIMIT 20` | 字段、过滤条件、排序不得改；SQL 须在围栏内 |
| g18 | create | 日志清理相关，如 `日志清理.md` / PowerShell 清理.md | `Get-ChildItem`、`-Recurse`、`Remove-Item`、`-WhatIf` | 参数与单引号路径保持原样；不得去掉 `-WhatIf` 直接给删除版 |
| g19 | create | 客户端配置相关，如 `API 客户端配置.md` / `客户端配置.md` | `timeout_seconds`、`max_retries`、`REPLACE-WITH-YOUR-KEY` | 键与值不得改；不得把占位符写成真实密钥，也不得编造密钥 |
| g20 | create | 默认参数相关，如 `默认可变参数.md` / `Python 陷阱.md` | `add_item`、`bucket`、`None` | 必须标明第一版是错的；不得把错误实现当作推荐写法 |
| g21 | append | `Go.md` | `append`、`cap`、`make` | 只追加，不得改成 replace；不得删除或改写 `## 控制流` 一节；备注须用 `>` |
| g22 | replace | `Python虚拟环境.md`（路径不得改） | `3.10`、`python -m venv` | `## 创建`、`## 常见问题`、一级标题须原文保留；不得改动其他章节内容 |
| g23 | append | `Kafka.md`（**不能写进** `RabbitMQ.md`） | `Kafka`、`消费者组`、`分区` | 只追加；不得删除 `## 分区`；不得改写 RabbitMQ 那份文件 |
| g24 | replace | `网络/HTTP缓存.md`（路径不得改） | `ETag`、`If-None-Match`、`304` | `## 强缓存`、一级标题须保留；不得改动强缓存一节的内容 |
| g25 | replace | `Python/工具函数.md`（路径不得改） | `max_delay`、`lru_cache` | `## 缓存` 及其 `@lru_cache(maxsize=32)` 代码须原样保留；不得删除重试一节 |

## modify 类不得删除的原有内容

| ID | 目标文件 | 原有内容（不得删除或改写） |
|----|----------|---------------------------|
| g21 | `Go.md` | `# Go`、`## 控制流` 整节（Go 只有 `for`、`if` 可带初始化语句、switch 自动 break） |
| g22 | `Python虚拟环境.md` | `# Python 虚拟环境`、`## 创建` 整节（含 `python -m venv .venv` 与激活命令）、`## 常见问题` 整节 |
| g23 | `Kafka.md` | `# Kafka`、`## 分区` 整节；另一份 `RabbitMQ.md` 完全不得改动 |
| g24 | `网络/HTTP缓存.md` | `# HTTP 缓存`、`## 强缓存` 整节（`Cache-Control: max-age` 一句） |
| g25 | `Python/工具函数.md` | `# 工具函数`、`## 重试` 标题、`## 缓存` 整节含 `@lru_cache(maxsize=32)` 代码 |

## 逐条补充断言

### dialogue（g01–g05）

- **g01**：必须区分「登录回归 → 李静」「搜索初版 → 李静」「发布窗口 10 月 15 日」「字段说明 10 月 9 日 → 李静」四项归属；`压测往后放` 要体现为延后而不是取消。允许把对话改写为陈述句，不允许改变归属和日期。
- **g02**：三要素齐全——定义（索引像目录，只存位置）、例子（订单表按用户号建索引）、限制（写入要维护索引、低选择性字段收益小）。只写结论即为失败。
- **g03**：必须区分「讨论过的方案：Redis、本地内存」与「已决定：Redis」，并写出理由（会话数据需跨实例读）。把两者都写成已决定即为失败。
- **g04**：现象（502 偶发）、无效尝试（看负载、重启 Nginx）、有效步骤（查错误日志 → 慢查询卡住连接池 → 加索引）按顺序保留；把重启 Nginx 写成解决方案即为失败。
- **g05**：最终结论只能是 `10 月 12 日凌晨两点`，`9 月 28 日` 与 `10 月 8 日` 若出现必须标明已作废及原因；预发布验证（10 月 11 日下午）不得遗漏。

### long_text（g06–g10）

- **g06**：定义/步骤/例子/限制四类都要在；`PRAGMA journal_mode=WAL;`、`PRAGMA wal_checkpoint(TRUNCATE);` 等语句原文保留；不得把 WAL 描述成查询加速。
- **g07**：前提、安装、执行、检查、恢复五节结构保留；恢复一节必须写明「配置结构未变才能只回退软链接，否则要连配置一起还原」这一条件；不得省略。
- **g08**：概念关系（幂等是重试的前提、不解决并发覆盖）、适用边界（有状态迁移、不可逆外部副作用）都要在；不得添加材料外结论。
- **g09**：三种方案与五个比较维度（依赖成本、精度、重试、观测、多实例去重）都要在；不得漏比较结论。
- **g10**：三条备注与三处例外都要保留，并落到 `>` 引用块；`通常 / 一般 / 建议 / 默认` 等限定语不得改成绝对说法；回滚的适用条件不得省略。

### english（g11–g15）

- **g11**：must 与 may 的强度差别必须体现（`must send the API key` 不能译成“可以”），`usually` 的默认语义要保留；`Authorization`、`Cache-Control`、`401` 原样。
- **g12**：`python -m http.server 8000`、`--directory ./site`、`netstat -ano | findstr :8000`、`Ctrl+C` 原样保留，不得改端口或省略选项。
- **g13**：`nonce`、`Content-Security-Policy`、`strict-dynamic`、`unsafe-inline` 不得翻译或改名；「nonce 不能跨请求复用」「两者同时出现时退回允许内联」两条限制不得丢。
- **g14**：gzip 12 MB → 约 2.4 MB / 约 1.1 秒，zstd level 3 → 约 2.1 MB / 0.4 秒，brotli quality 5 → 约 2.2 MB / 0.7 秒，100 MB 归档 gzip 9.5 秒 / zstd 2.8 秒，均不得改动或张冠李戴。
- **g15**：现象（02:14 UTC 起 503 约 11 分钟）、根因（重建索引先删别名）、workaround（别名指回旧索引，约 90 秒恢复）、后续修复（写临时索引再切别名）四者分开；不得把 workaround 写成根因修复。

### code（g16–g20）

- **g16**：`def retry_delay(attempt, base=0.5, max_delay=30)`、`min(delay, max_delay)` 与三个阶段返回值 `0.5 / 4.0 / 30` 都要在；代码须在 ```python 围栏内；不得把返回值写成字符串。
- **g17**：建表字段六个齐全，查询保留 `WHERE user_id = ?`、`status = 'paid'`、`amount > 100`、`ORDER BY created_at DESC`、`LIMIT 20`；不得改写排序或漏过滤条件。
- **g18**：三条命令的参数、单引号路径 `'D:\backup'`、`-WhatIf` 都要在；不得把 `-WhatIf` 版删掉只留正式删除版，或把 `-WhatIf` 写成推荐的生产命令。
- **g19**：六个键与取值都要在（含占位符 `REPLACE-WITH-YOUR-KEY`）；`max_retries=3` 表示最多 4 次请求这一说明不得丢；不得编造真实密钥。
- **g20**：错误版与修正版都要在，且必须明确标出第一版是错误的、错因是默认可变参数共享；不得把 `def add_item(item, bucket=[])` 写成推荐写法。

### modify（g21–g25）

- **g21**：`append`，目标必须是 `Go.md`；新增 `## 切片` 一节；`## 控制流` 原文不得改动；切片共享底层数组的备注须用 `>`。
- **g22**：`replace`，路径必须是 `Python虚拟环境.md`；`## 适用版本` 更新为 3.10 及以上；`## 创建`、`## 常见问题` 原文保留；正文须含一级标题。
- **g23**：`append`，目标必须是 `Kafka.md`；不得写入或改动 `RabbitMQ.md`；`## 分区` 原文保留。
- **g24**：`replace`，路径必须是 `网络/HTTP缓存.md`；`## 协商缓存` 补全为 `ETag` / `If-None-Match` / 304 与 `Last-Modified` 版本；`## 强缓存` 原文保留。
- **g25**：`replace`，路径必须是 `Python/工具函数.md`；重试函数签名改为含 `max_delay=None`；`## 缓存` 与 `@lru_cache(maxsize=32)` 原样保留。

## 已知 L1 子指标偏差（供审查时对照，不作为推翻结论的依据）

这些是 L1 打分器的既有口径，不是产品缺陷。审查时如遇下列命中，按内容判据结论为准，并在报告中记录。

| 指标 | 现象 | 相关条目 |
|------|------|----------|
| `faithful.hedge` | 材料含 `may/usually` 等情态词时，草稿出现 `必须` 即判 0。g11 要求区分 must 与 may，忠实译出 `必须` 会被该指标命中 | g11（设计内的张力）；g06–g10、g19 已移除材料中的强化词以避免假信号 |
| `form.list` | 列表行占比 > 50% 判 0。命令/步骤类材料整理成步骤列表时容易被命中 | g12、g16–g19 |
| `complete.compression` | `faithful_paragraphs` 下草稿与材料长度比 < 0.55 判 5、< 0.35 判 0。长文压缩过度会被命中 | g06–g10 |
| `retrievable.file_name_topic` | 需要 `stem` 与锚点有重叠；文件名不含锚点时只给 5 分 | 全部条目 |

## 与旧集的关系

- `cases.jsonl` 的 20 条继续作为行为/正文回归单独运行，结果与 g 集分开计数，不合并分母。
- `learning_notes.jsonl` 的 v0.2 加工分**不是** V1 的退出门槛，本集不引用它的分数。
- 本集不新增运行时评分、不新增自动审批流程，也不写入用户 `notes/`。
