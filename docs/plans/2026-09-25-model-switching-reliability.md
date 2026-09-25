# 模型切换与检索可靠性修复计划

> **交给 Claude Code 执行：**按任务逐项实施，遵循仓库现有 Python、FastAPI、Pydantic、LangChain、原生 JS 与测试规范。先阅读 `CLAUDE.md`、`docs/plans/2026-09-25-model-switching-ui.md`、`docs/architecture/architecture.md`、`docs/architecture/retrieval.md` 和相关模块 README。不得覆盖或重置用户已有改动；本计划只描述实现工作，不授权合并或发布。

**目标：**修复聊天配置激活一致性、多个模型凭证的持久管理、向量索引重建失败和丢失索引误报可用的问题，并补上并发发送和错误提示回归。

**设计：**聊天配置的持久保存与运行时激活是两个独立操作。已保存的 profile 应可重复选择；只有显式删除才删除 profile，更新一个 profile 不得覆盖其它 profile。密钥按 profile 保存，环境变量只作为首次初始化/兼容的默认凭证来源，不把其它 profile 的密钥合并进单一环境变量。聊天激活必须在验证和新 Agent 构造成功后，原子发布同一份运行时快照。向量索引目标由嵌入模型、模型版本、分块策略、标题前缀等完整配置指纹唯一标识；重建先写入隔离的新索引，校验成功后再切换 active 指针。活动 collection 缺失或元数据指纹不匹配时必须报告 unavailable/incomplete，显式修复后才恢复可用。

**技术栈：**Python 3.13+、FastAPI、Pydantic、LangChain、Chroma、SQLite/文件存储（沿用现状）、原生 JavaScript、pytest。

**依据：**已有模型切换计划及 `src/noteagent/model_management/`、`src/noteagent/bootstrap/runtime.py`、`src/noteagent/retrieval/`、前端模型设置组件。

## 约束与数据安全

- 不增加外部模型、向量数据库或前端框架依赖；保持现有本地 Chroma 部署方式。
- API Key 不得出现在 GET 响应、错误响应、日志、前端 DOM 文本、测试快照或诊断输出中；profile 输出仅返回 `has_api_key` 等布尔状态。
- 配置更新遵循 revision/冲突检测和原子写入；并发请求不能静默丢失其它 profile 或 active 指针。
- 活动聊天 profile 不得通过普通保存接口替换运行中的 Agent；只能经显式激活流程切换。
- 向量重建失败时旧索引和旧 runtime snapshot 保持可用；未验证的新 collection 不得发布为 active。
- 不修改笔记原文，不对现存用户 collection 做破坏性清理；旧索引兼容和恢复必须有显式迁移/重建路径。
- 最终运行仓库相关单元、集成测试及完整测试；记录失败和环境限制，不得把测试替身结果描述成真实供应商验证。

## 文件职责地图

| 文件 | 计划中的职责 |
|---|---|
| `src/noteagent/model_management/schemas.py` | profile 写入、删除、凭证来源、索引 job/status 的验证契约 |
| `src/noteagent/model_management/store.py` | profile 集合持久化、密钥保留/替换/清除、兼容旧配置 |
| `src/noteagent/model_management/service.py` | 保存/激活/删除事务、运行时快照原子替换、索引目标生成/重建/发布、健康检测 |
| `src/noteagent/model_management/router.py` | profile 删除路由、请求和错误语义、状态输出 |
| `src/noteagent/bootstrap/runtime.py` | profile 的凭证解析与 LangChain 模型构造边界 |
| `src/noteagent/retrieval/vector_store.py`、`src/noteagent/retrieval/service.py` | collection 存在性、元数据指纹校验、可区分空索引和缺失索引 |
| `src/noteagent/web/static/model-settings.js`、`.css` | 保存/编辑/激活/删除多个 profile 的交互，以及对应弹窗内错误展示 |
| `src/noteagent/web/templates/home.html` | 聊天提交互斥状态，防止重复发送 |
| `tests/unit/test_model_settings_store.py`、`tests/unit/test_model_management.py` | 凭证与存储、激活事务、索引状态与恢复单元测试 |
| `tests/integration/test_model_settings_api.py`、`tests/integration/test_retrieval_service.py`、`tests/integration/test_app.py` | API、实际 Chroma、并发及运行时集成回归 |
| `docs/architecture/{architecture.md,retrieval.md,frontend.md}`、`src/noteagent/model_management/README.md` | 同步最终状态语义、迁移、恢复和安全说明 |

若实现前发现真实代码职责与上表路径不同，应遵循现有模块边界，将同一职责落在当前对应模块，并在最终报告说明实际改动路径。避免为这次修复大规模重构 955 行的 service；只有能隔离并测试生命周期边界时才抽出小模块。

---

### 任务 1：激活聊天 profile 时保持 UI、配置和 Agent 一致

**文件：**`service.py`、必要时 `schemas.py`/`router.py`；测试 `test_model_management.py`、`test_model_settings_api.py`。

- [ ] 为当前 active profile 的普通 `POST /chat/profiles` 创建路径和 `PUT /chat/profiles/{id}` 更新路径写失败测试：提交体中的 `id` 不得覆盖路由身份；新 profile ID 由服务端生成；active profile 不可通过普通保存改变；其它 profile 不受影响。
- [ ] 写激活事务测试：候选模型构造失败、供应商探测失败或 revision 在探测期间改变时，active profile、revision、runtime snapshot、旧 Agent 对象均不改变。
- [ ] 写成功激活测试：成功后 `status().active_chat`、持久化 active ID、runtime snapshot profile ID 与新 Agent 配置一致；保存草稿不激活，激活才更换 Agent。
- [ ] 修复请求身份解析：create 路由忽略/拒绝用户指定 ID 并产生新 ID；update 路由以 URL `profile_id` 为唯一身份，body ID 若提供必须匹配 URL，否则 422/409；active ID 统一由 activate 事务切换。
- [ ] 将激活实现整理为 prepare/commit 两阶段：在锁外探测和构造 Agent；提交前重新核对 revision、maintenance 状态和目标 profile；在同一个锁内持久化新 profile/active ID 并发布完整 `RuntimeSnapshot`。持久化失败时不得发布新 snapshot。
- [ ] 运行上述单项测试及 `uv run pytest tests/unit/test_model_management.py tests/integration/test_model_settings_api.py -q`。

### 任务 2：支持多个已配置模型及其 Key 的持久管理

**文件：**`schemas.py`、`store.py`、`service.py`、`router.py`、前端 `model-settings.js`/`.css`；测试 `test_model_settings_store.py`、`test_model_settings_api.py`。

- [ ] 固化 profile 数据规则并测试：配置文件保存 profile 列表；新 profile 与现有 profile ID 不冲突；编辑一个 profile 只更新该 ID；删除一个非 active profile 只删除该 ID；active profile 不能直接删除，须先切换到另一个 profile；配置仅在用户显式删除时移除。
- [ ] 固化密钥更新语义并测试：未提交 `api_key`/“保留已保存 Key”时编辑保留当前 profile 的 Key；提交新的非空 Key 才替换该 profile 的 Key；显式“清除此 Key”才清空；创建 profile 的 Key 仅写入新 profile。任何操作不得覆盖其它 profile 的 Key。
- [ ] 环境变量 profile 作为兼容的只读来源或可复制来源：`.env` Key 不写入配置文件；从环境默认 profile 切换供应商时，不能把 `credential_source=env` 沿用到不匹配的供应商。要求用户为新 profile 提供 Key，或选择明确的无密钥认证模式；启动时遇到缺少所需 Key 的 active profile，报告可操作的配置错误，不静默退回另一个模型。
- [ ] 增加删除接口和响应契约（如 `DELETE /model-settings/chat/profiles/{profile_id}`），加入 revision 检查、同源校验、active profile 删除保护，以及前端确认/刷新。
- [ ] 为旧 `settings.json` 格式写迁移测试：保留已有 profile ID、active 指针和可用凭证来源；迁移失败保留原文件并报可诊断错误。禁止静默重置配置。
- [ ] 存储仍采用同目录临时文件 + fsync + 原子替换，并维持仅当前用户可读写的文件权限。确认 Windows 上权限行为不导致启动失败；密钥字段序列化不得通过 `model_dump()` 变成掩码字符串。
- [ ] 更新聊天设置 UI：列出所有保存的 profile、显示当前 active 状态；用户可选择已有 profile 激活、编辑、创建、删除。Key 输入默认留空代表保留已有 Key；提供明确清除操作；仅显示“已配置/未配置”，绝不回显 Key。测试错误显示在当前打开的聊天 profile 弹窗。
- [ ] 测试跨供应商重启：为 DeepSeek 和 OpenAI-compatible 分别保存两个 profile 与不同测试 Key；激活其中一个、重启 service 后，两 profile 均存在，各自 Key 仍分别匹配，active profile 仍一致；响应和日志中两个 Key 字符串均不存在。
- [ ] 运行 `uv run pytest tests/unit/test_model_settings_store.py tests/unit/test_model_management.py tests/integration/test_model_settings_api.py -q`。

### 任务 3：修复更改分块配置后相同模型无法重建

**文件：**`service.py`、`retrieval/vector_store.py`、`retrieval/service.py`、必要时 `bootstrap/runtime.py`；测试 `test_model_management.py`、`test_retrieval_service.py`。

- [ ] 增加失败测试：用真实临时 Chroma 首先建立 e5 + 配置 A collection；切换到不同 chunk strategy 或 heading prefix 配置 B；同一模型再次请求修复时必须启动新 job 并成功，不能重开配置 A collection 后抛 `IndexConfigMismatch`。
- [ ] 定义稳定的索引身份：canonical fingerprint 至少包括嵌入模型 ID、resolved revision（适用时）、chunk strategy、chunk size/overlap、heading prefix 策略和文档规范化版本。对 canonical JSON 做 SHA-256；只用模型 ID 作为 collection 名称不符合要求。
- [ ] 使用 fingerprint 派生安全且有长度上限的 collection 名称；相同模型不同指纹必须写到不同 collection；相同完整指纹可识别为已建索引。collection metadata 保存 fingerprint 及可核验配置字段，旧格式 collection 标记为需验证或需重建，禁止伪造匹配。
- [ ] 保持 build-then-publish：新 collection 独立构建并完成完整 corpus 同步、抽样查询/完整性验证后，在配置文件一次性提交 active embedding 和 collection；提交前 revision/corpus manifest 变化则不发布。失败保留旧指针和旧 collection。
- [ ] 定义旧索引回收策略：首次只保留旧 collection，不随重建自动删除；只有验证新索引已经 active 且没有运行中的请求引用旧 snapshot 后，才允许单独执行可恢复/可重试的清理。若当前仓库没有安全引用计数，不实现自动清理。
- [ ] 运行 `uv run pytest tests/unit/test_model_management.py tests/integration/test_retrieval_service.py -q`，并确认原有模型切换、回滚、job 重启恢复用例仍通过。

### 任务 4：让缺失或损坏的活动索引准确显示并幂等修复

**文件：**`retrieval/vector_store.py`、`retrieval/service.py`、`service.py`、`schemas.py`、`router.py`、前端 `model-settings.js`；测试 `test_retrieval_service.py`、`test_model_management.py`、`test_model_settings_api.py`。

- [ ] 为真实 Chroma collection 写测试：collection 缺失、元数据指纹不符、collection 存在但为空、有效 corpus 本身为空，这四种情况应可区分。只有最后两种在配置和 corpus 均有效时可报告可用（空 corpus 可用但显示 0 个已索引文件）。
- [ ] 删除 active collection 后重启 service：状态必须 `retrieval_available=false` 并提供稳定的 `retrieval_problem`/状态码；严禁在健康检查/普通 search 初始化中用 `get_or_create_collection` 静默创建空集合并宣称有效。
- [ ] 将 “ensure/open existing” 与 “create collection for rebuild” 分开。普通读取必须仅打开存在集合并验证 metadata；缺失时不得创建；只有新的 rebuild job 可创建指纹命名的新集合。
- [ ] 为同一模型/指纹的显式重试定义幂等规则：如果当前 active collection 存在且指纹正确，返回 `unchanged=true`、不创建 job；如果 active 指针所指 collection 缺失/不完整，必须创建修复 job；如果相同指纹有正在运行的 job，返回该 job 或明确 409，不重复启动第二个 worker；失败重试生成可识别的新 job，保留旧 active 状态（若旧集合也丢失则持续报告 unavailable，直到修复成功）。
- [ ] 增加并发和崩溃恢复测试：两个相同 switch 请求不会并发写同一目标 collection；进程在构建后、发布前中断时 active 指针不变；重启识别遗留 job 并能安全重试或标记失败。
- [ ] 前端将缺索引、配置不匹配、修复进行中和修复失败分别展示；重试使用当前 revision，按钮状态与服务端状态刷新一致。
- [ ] 运行 `uv run pytest tests/integration/test_retrieval_service.py tests/unit/test_model_management.py tests/integration/test_model_settings_api.py -q`。

### 任务 5：补齐交互回归并同步架构说明

**文件：**`home.html`、`model-settings.js`、前述测试文件、`docs/architecture/architecture.md`、`docs/architecture/retrieval.md`、`docs/architecture/frontend.md`、`src/noteagent/model_management/README.md`。

- [ ] 给 `ask()` 加同步互斥门闩：在任何 `await`（包括 `refreshIfStale()`）之前立即标记提交进行中；第二次调用立刻返回。所有同步创建会话、读取问题、清空输入和流式过程都由同一状态保护；异常和取消路径在 `finally` 释放状态，失败请求按既有行为恢复问题文本。
- [ ] 添加可重复 UI/API 测试：将 `/model-settings` 响应延迟 1 秒并连续触发两次发送；恰好产生 1 个 `/chat` 请求、1 条用户消息和 1 个会话。再测试失败返回后门闩释放，可重新发送。
- [ ] 将 `switchEmbedding()` 的成功、错误、未变化消息全部写入向量设置弹窗自己的状态区；聊天 profile 操作错误只进聊天弹窗。添加 JS 层测试或现有浏览器自动化断言覆盖 HTTP 错误与网络异常。
- [ ] 更新架构文档：profile 多配置/Key 生命周期/环境变量迁移，运行时激活原子性，索引 fingerprint 与 collection 生命周期，丢失检测、空语料语义、修复/重试幂等行为。
- [ ] 更新部署说明和 `.env.example`：解释 `.env` 仅提供默认/兼容 profile，用户新增模型凭证存储在哪里、如何备份、如何显式删除，以及容器持久卷要求。确保文档与实现的密钥保护能力一致，不宣称加密静态密钥，除非实际加入且验证了加密方案。
- [ ] 完整验证：`uv run pytest tests/unit/test_model_settings_store.py tests/unit/test_model_catalog.py tests/unit/test_model_management.py tests/unit/test_llm_factory.py tests/integration/test_model_settings_api.py tests/integration/test_retrieval_service.py tests/integration/test_notes_api.py tests/integration/test_app.py -q`，随后 `uv run pytest tests -q`。
- [ ] 执行 `git diff --check`、检查 `git status`，确认未覆盖用户现有改动；报告修复项、实际测试数、未通过项、配置迁移和运维注意事项。不要合并分支或发布。

## 完成验收标准

1. 普通编辑绝不改变当前运行 Agent；一次成功激活后 UI、持久状态与运行 Agent 一致，失败时旧状态完整保留。
2. 两个不同供应商的 profile 和 Key 可同时保存、重启后各自恢复；单 profile 更新/删除不会影响其他 profile；Key 只有显式清除/删除 profile 才被移除。
3. 相同嵌入模型在 chunker 配置改变后可建立新的隔离索引；校验成功才原子激活，失败保留旧索引。
4. 缺失 collection 不被误认为可用；有效空语料与丢失索引可区分；重复 switch 请求符合幂等规则并可恢复。
5. 快速双击聊天只提交一次；向量切换错误显示在正确弹窗。
6. 所有密钥不回显、不进日志；原有 RAG 笔记和其他模型 profile 未被意外修改。

## Claude Code 执行提示

```text
请执行 docs/plans/2026-09-25-model-switching-reliability.md。先阅读计划中列出的仓库规范和关联模块文档，检查当前 git 状态并保留所有既有改动。按任务先写失败测试再做最小修复，每个任务完成后运行对应测试。不要合并分支、发布或修改用户笔记。完成后运行计划列出的完整测试与 git diff --check，并按验收标准汇报结果、风险和尚未完成项。
```

---

## 执行结果（2026-09-26）

分支 `fix/model-switching-reliability`（基于 `main`）。上面的清单是原始规格；下面是按任务的实际落地情况与偏差。

### 9.1 任务完成情况

| 任务 | 状态 | 落地说明 |
|---|---|---|
| 1 激活一致性 | 完成 | create 由服务端生成 id（忽略 body id）；update 以 URL 为唯一身份、body id 不一致报 422；active 不可普通保存/删除；`activate_chat` 拆成 `_prepare_activation`（锁内解析 + 锁外探测与构造）与 `_commit_activation`（锁内复核 revision/维护状态、写盘、发布） |
| 2 多 profile 与 Key | 完成 | profile 增删改只影响该 id；Key 留空保留 / 新 Key 替换 / 显式 `clear_api_key` 清除；`DELETE /model-settings/chat/profiles/{id}?expected_revision=N`（同源校验、active 保护、204）；env 凭据不再跟着换供应商（报 422）；旧 `settings.json`（无 `schema_version`）按 legacy 读入且保留 id/active/凭据，更高版本报错并保留原文件 |
| 3 索引身份与重建 | 完成 | 身份改为 canonical JSON 的 SHA-256（model、resolved revision、chunker、heading prefix、instructions、normalization、schema）；collection 名由指纹派生（摘要 16 位、总长 ≤63、摘要不截断）；同模型换分块配置 → 新 collection、不再撞 `IndexConfigMismatch`；装配后指纹与预计算不符则放弃发布；旧 collection 不自动删除 |
| 4 缺失/损坏索引 | 完成 | `create_if_missing=False` 的读取路径（缺失报 `CollectionMissingError`，绝不 `get_or_create`）；`retrieval_state` = `ok`/`empty`/`missing`/`config_mismatch`/`unavailable` 加上 `indexed_files`/`corpus_files`；`GET /model-settings` 每次 `verify_index()` 复核，删库后立刻变色；幂等/重试矩阵见 [retrieval.md](../architecture/retrieval.md) §7.1 |
| 5 交互回归与文档 | 部分 | `ask()` 同步门闩、向量消息只进向量弹层、前端区分四种索引状态、文档与 `.env.example` 全部更新；**未加自动化 UI 回归测试**（见 9.4） |

### 9.2 测试

`uv run pytest tests -q` → **470 passed**（本机用 `.venv/Scripts/python.exe -m pytest`，`uv run` 在 Git Bash 下报 trampoline 错误）。

新增/改写的用例（全部通过）：`tests/unit/test_model_management.py`（49）、`tests/unit/test_model_settings_store.py`（22）、`tests/unit/test_embedder.py`、`tests/integration/test_model_settings_api.py`、`tests/integration/test_retrieval_service.py`。覆盖：请求身份、delete 的 revision/active 保护、激活失败不动旧状态、env 凭据迁移、跨供应商重启、legacy 配置读入、未来 schema 拒绝、分块配置变化后重建（真实 Chroma）、删除活动 collection 后报 `missing` 并修复、并发 switch 拒绝、发布前退出不动指针、空语料可用、四种索引状态区分。

### 9.3 浏览器验收（隔离实例，真实 MiniLM）

用一个临时实例（SQLite + 临时 `notes`/`chroma`/`model_settings`，`EMBEDDING_CACHE_DIR` 只读复用本机缓存）在真实浏览器里跑通：

| # | 结果 | 说明 |
|---|---|---|
| 1 | ✅ | 启动时索引不存在 → 向量弹层显示「索引 collection「browser_check」不存在…请重建索引」，活动模型行按钮为「重建并修复」+「索引不可用」；`retrieval_state=missing`、`corpus_files=2`、`indexed_files=0` |
| 2 | ✅ | 点「重建并修复」→ 真实加载 MiniLM 并建索引，进度按阶段推进；完成后只有一个 collection `browser_check__all-MiniLM-L6-v2-dce31fc4f6198bc4`（0 个残留空集合），metadata 同时含指纹与可核验字段；`active_embedding` 记录 model/revision/collection/fingerprint；状态变 `ok`、`indexed_files=2` |
| 3 | ✅ | 聊天弹层：新增配置走「保存」→ 列表出现非当前项（启用/编辑/删除）且提示「已保存（未启用）」，active 不变；「编辑」时 Key 提示「留空保留已保存的 Key」、出现「清除已保存的 Key」；编辑后 Key 仍为「已保存 Key」（`settings.json` 里 `api_key` 原样保留，env 那条仍为空）；「删除」经 confirm 后从列表消失；编辑当前启用项时「保存」按钮不出现并提示只能用「保存并启用」 |
| 4 | ✅ | 双击发送（把 `/model-settings` 延迟 1 秒后同 tick 调用两次 `ask()`）：`/chat` 恰好 1 次、用户消息恰好 1 条、助手消息 1 条；服务端返回 409 时问题文本还原到输入框、`isStreaming` 释放、再次发送能真的发出（`/chat` 计数 +1） |

未截屏：本机 in-app 浏览器没有可截图的可见表面（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`），因此上面是 DOM/接口断言与集合元数据证据，不是截图。

### 9.4 未完成项与已知风险

- **双击发送没有自动化回归测试**：仓库没有 JS 测试设施，也没有浏览器自动化用例目录（`tests/e2e/` 只有 README）。上面的第 4 项是手工浏览器验证，**不能进 CI**。要变成可重复测试需要引入前端测试设施或浏览器自动化，本计划没有授权新增依赖。
- **未验证真实供应商**：本轮没有可用的 DeepSeek/兼容服务探针，激活聊天配置的成功路径仍只有单测与假探针覆盖（沿用上一份计划的缺口）。
- **迁移影响（重要运维事项）**：索引身份换了算法，collection 名从 `{base}__{模型短名}` 变成 `{base}__{模型短名}-{指纹摘要}`。升级后**启动即报索引不可用（`missing` 或 `config_mismatch`）**，必须在界面点一次「重建并修复/重建并切换」（或跑 `scripts/index_notes.py --all`）重建索引。旧 collection 仍在盘上，不会自动删除；确认新索引可用后可自行清理。`settings.json` 不需要迁移，旧文件按 legacy 读入。
- **`.env` 的 Key 与「环境默认」配置绑定**：把那条配置改成非 DeepSeek 供应商会被拒（要求另填 Key）。这是有意的，但用户读到报错前可能不理解，文档已说明。
- **CLI 不写 active 指针**：`scripts/index_notes.py` 只重建数据，指针仍由界面发布；两者不能同时运行（单 worker 限制已写入文档）。
- **Windows 权限**：`chmod 600` 在 Windows 上基本无效，`settings.json` 的实际保护取决于用户目录 ACL；文档没有宣称加密。
- **未提交**：本分支未合并、未推送；工作区里 `docs/references/思考.md` 的改动与另外两个未跟踪文档属于用户自己的内容，未纳入本次提交。

### 9.5 变更文件

新增：`src/noteagent/retrieval/instructions.py`。

修改：`src/noteagent/{bootstrap/runtime.py,model_management/{catalog,router,schemas,service,store}.py,retrieval/{embedder,service,vector_store}.py}`、`scripts/index_notes.py`、`src/noteagent/web/static/model-settings.{js,css}`、`src/noteagent/web/templates/home.html`、`tests/{unit/{test_embedder,test_model_management,test_model_settings_store}.py,integration/{test_app,test_model_settings_api,test_notes_api,test_retrieval_service}.py}`、`docs/architecture/{architecture,frontend,retrieval}.md`、`src/noteagent/model_management/README.md`、`src/noteagent/retrieval/README.md`、`README.md`、`.env.example`、`docker-compose.yml`。
