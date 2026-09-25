# 聊天模型与本地向量模型切换执行计划

> 给 Claude Code：逐任务实施、检查并勾选。本文件只定义待实现功能；编写计划的阶段不修改应用代码。可使用执行环境已有的 executing-plans 技能，缺少技能不影响按本文执行。

**Goal:** 在聊天输入框下方靠右提供聊天模型和向量模型两个入口，支持配置聊天服务、切换已下载的向量模型，并使界面、实际请求、索引和重启后的状态一致。

**Architecture:** 维持现有 FastAPI、原生 HTML/JS、LangChain ChatAgent 和本地 Chroma。新增小型模型管理模块管理配置、当前运行对象及向量重建任务；bootstrap 负责装配。聊天切换对后续请求生效；向量切换构建独立索引，成功后统一发布新的 retrieval 与绑定该 retrieval 的 Agent。

**Tech Stack:** 现有 Python 3.13+、FastAPI、Pydantic、LangChain、sentence-transformers、Chroma、原生 JavaScript/CSS。已有 langchain-openai 与 langchain-deepseek，第一期不引入前端框架、任务队列或新的模型 SDK。

**Spec:** 本文是执行规格。先阅读 `CLAUDE.md`、`docs/architecture/frontend.md`、`docs/architecture/retrieval.md`、`docs/architecture/chat-tools.md`，以及现有 RAG 优化计划和报告。用户明确要求两个入口位于聊天输入框下侧靠右，聊天配置可填写 URL/Key，向量模型选择当前已下载项。

## 1. 范围与交互决定

1. 本项目是本地单用户应用，本期模型选择为应用全局设置，影响所有会话的后续请求。切换不会创建新会话或丢弃会话历史、摘要、引用、待审草稿。
2. 聊天配置保存为具名 profile，用户可新增、编辑、选择；提供模型名、Base URL、API Key，以及 provider（DeepSeek / OpenAI-compatible）、上下文窗口。先支持项目已有 SDK 对应协议，不声称任意协议只填 URL 都能运行。
3. 输入框下方右侧显示 `聊天：模型名 ▾` 和 `向量：模型名 ▾`。点击聊天按钮显示已保存配置及“添加/编辑”；点击向量按钮显示服务端发现的本地候选及当前状态。
4. 向量选择后的操作按钮叫“重建并切换”，说明“重建期间暂不可发送消息或保存笔记，已有内容仍可查看”。用户点击即开始，不再套多层确认。
5. 聊天设置面板提供“测试连接”和“保存并启用”。保存并启用先测试实际流式响应和工具调用协议，再提交配置；测试不读取用户笔记、不写入会话，使用小型固定探针。
6. 聊天切换不影响正在生成的一轮；当前页面生成期间禁用切换操作，后端仍要支持另一个标签页切换时旧轮持有旧对象。
7. 向量重建只允许一个任务。第一期单进程单 worker；后台任务通过受管理线程/异步任务执行，重建期间允许读笔记、读历史和查看状态，拒绝新聊天及笔记修改，避免漏掉构建期间的新增/修改/删除。
8. 初次启动从环境配置生成“默认配置”。已有 UI 持久配置优先于环境中的模型选择，前端显示配置来源。环境仍负责服务器、数据库、笔记目录和缓存根目录；UI 不覆写 `.env`。
9. 本期不做远程向量 API、模型下载管理、自动删除旧索引、任意多供应商插件系统或每会话向量模型。

## 2. 当前代码连接点（执行前重新核对）

| 文件 | 当前职责 | 本次关联 |
|---|---|---|
| `web/templates/home.html` | 约 922 行 input-area，question 输入框；约 980 行起内联 JS；isStreaming 与发送逻辑 | 新增底部右侧按钮、面板和状态；保留现有键盘、SSE、草稿逻辑 |
| `web/__init__.py` | read_home_html 直接返回静态模板正文 | 若新 JS/CSS 外置，必须在 FastAPI 显式挂载 static，不能假定模板自动提供资源路由 |
| `llm/factory.py` | create_chat_model / create_judge_model，provider 当前固定 deepseek | 增加显式运行配置入口，保留旧 Settings 包装函数与 Judge 行为 |
| `chat/agent.py` | 构造时捕获 model、tools、retrieval、budget；bind_tools；摘要也用 self._model | 切换须重建 Agent，不能只改 Settings 或单独修改私有 _model |
| `chat/tools.py` | 工具闭包捕获 retrieval、notes、drafts | 更换 retrieval 时重建工具，再构造新 Agent |
| `chat/router.py` | container.chat_agent；resolve_conversation；SSE；review | 请求先取得当前运行快照，重建忙碌检查在创建会话/写消息之前执行 |
| `notes/router.py` | container.retrieval；创建/保存/删除/移动/文件夹操作/手动索引 | 使用同一运行快照与写操作门禁，不能继续写旧 collection |
| `bootstrap/app.py` | AppContainer、build_container、create_app、lifespan | 装配管理器、初次运行对象、路由和任务收尾 |
| `bootstrap/settings.py` | 默认 e5-small、heading 切块；本地环境可覆盖 | 新增运行配置存储目录设置，保留部署配置与显式默认优先级 |
| `retrieval/embedder.py` | build_embedder、MODEL_INSTRUCTIONS | 复用已支持模型的 query/document 指令，不直接绕过 build_embedder |
| `retrieval/service.py` / `vector_store.py` | 配置指纹、索引、Chroma collection | 新 collection 全量构建；禁止覆盖指纹将旧向量冒充新模型 |
| `scripts/index_notes.py` | 批量索引入口 | 提取可复用索引目标枚举，CLI 与 UI 使用相同过滤规则 |
| `docker-compose.yml` / Dockerfile | 镜像默认缓存 e5；当前未挂载完整运行配置目录 | 持久化 UI 配置，候选必须按容器可访问的缓存列举 |

当前宿主缓存中观察到 MiniLM、bge-small-zh-v1.5、multilingual-e5-small 三个目录。目录存在不证明下载完整；不得在 UI 硬编码“已可用”。实际缓存根取 Settings，不能写死开发者 Windows 路径。

## 3. 文件划分与依赖方向

新增 `src/noteagent/model_management/`：

- `schemas.py`：请求/响应及内部配置结构；敏感内部类型与公共响应分开。
- `store.py`：具版本号的本地 JSON、原子替换、当前 active 指针及 profile 持久化；无 HTTP/模型调用。
- `catalog.py`：枚举已知支持模型的缓存快照、检查本地文件并输出候选；无下载。
- `service.py`：聊天候选验证、运行对象快照、发布、操作门禁、重建任务生命周期。
- `router.py`：参数校验、调用 service、映射状态码；不装配模型、不扫描文件。
- `__init__.py` 和简短 `README.md`：公开边界与运行说明。

按需要新增 `bootstrap/runtime.py` 存放唯一的 Agent/工具装配函数；由 bootstrap 注入 management service，避免 management 反向导入 app 形成循环。LLM factory 只接受明确参数/Settings，不依赖 HTTP 或 management service；retrieval 不 import chat 或 management。

新增 `web/static/model-settings.js`、`web/static/model-settings.css`。只把本功能代码外置，不搬迁整个现有页面。新增测试 `test_model_settings_store.py`、`test_model_catalog.py`、`test_model_management.py`、`test_model_settings_api.py`，沿用现有测试目录规范。

## 4. 配置和 API 契约

内部 ChatProfile：id、label、provider、model、base_url、api_key（SecretStr）、auth_mode（api_key / none，默认 api_key）、context_window。provider 固定为 deepseek / openai-compatible；公开 ChatProfileOut 除去 api_key，增加 has_api_key、source。auth_mode=none 仅适用于用户明确选择的无需认证兼容服务；DeepSeek 仍要求 Key。

更新 profile 时省略 api_key 表示保留；清空须显式 clear_api_key=true，禁止把掩码字符串当真实 Key 保存。新建允许空 Key 的本地兼容服务；SDK 若要求非空占位，只在客户端内部按该 profile 的显式“无需 Key”设置使用，不影响真实认证配置。

持久化至 `MODEL_SETTINGS_DIR`（默认 `var/model_settings`）下 `settings.json`：schema_version、revision、chat_profiles、active_chat_profile_id、active_embedding(model_id、resolved_revision、collection、fingerprint)。秘密只在服务端本地文件保存，不进 Git、localStorage、sessionStorage、URL、日志或 API GET 响应。文档如实说明本期是本地凭据文件，不宣称加密；文件权限按当前平台限制为应用用户可用。

环境提供的 Key 用凭据来源引用表示，加载时从 Settings 解析，无需复制到 UI 配置文件。用户手动填写的 Key 可持久化在上述服务端文件；响应只返回 has_api_key。UI 编辑时密码框空白且提示“留空保留”。

| 方法与路径 | 请求 | 成功响应/行为 |
|---|---|---|
| GET `/model-settings` | 无 | revision、脱敏 profiles、active_chat、active_embedding、embedding_job、busy 状态 |
| POST `/model-settings/chat/test` | 候选 profile 字段；编辑可带 id 复用旧凭据 | verified、streaming、tool_calling；不保存、不切换 |
| POST `/model-settings/chat/profiles` | 完整 profile 字段、expected_revision | 201 保存的脱敏 profile；仅保存配置，不启用 |
| PUT `/model-settings/chat/profiles/{id}` | profile 字段、expected_revision | 更新脱敏 profile；已激活项的编辑必须经激活事务，不能改文件后仍运行旧客户端 |
| POST `/model-settings/chat/activate` | profile_id 或候选 profile（二选一）、expected_revision | 测试、保存和启用作为一次事务；返回新的 revision 和 active_chat |
| GET `/model-settings/embeddings` | 无 | model_id、label、availability、reason、active；不返回绝对缓存路径 |
| POST `/model-settings/embedding/switch` | model_id、expected_revision | 202 job；同 active 且指纹一致返回 200 unchanged |
| GET `/model-settings/jobs/{id}` | 无 | status、stage、completed、total、active_model、target_model、可公开的 error |

状态码：422 参数无效；404 未知 profile/job/model；409 过期 revision、重复任务或应用正忙；502 模型服务拒绝/协议不支持；504 超时。统一错误结构 code/message/retryable；具体服务异常不原样透出 Key、Authorization、带凭据 URL。

URL 校验允许 http/https 和显式 localhost 服务，拒绝 URL 内嵌 userinfo。表单描述 Base URL 的含义，避免用户填 `/chat/completions` 后端再拼一次；不盲目给所有 provider 加 `/v1`。调用超时、响应长度和探针请求数有明确上限（每次测试最多 2 个短请求、每个 20 秒、无无限重试）。测试连接会发送请求，按钮说明即可。

## 5. 一致性和生命周期要求

### 5.1 运行快照与发布

RuntimeSnapshot 至少包含 chat_profile_id、chat_agent、retrieval、embedding_model_id、collection、revision。单一 service 持有当前快照；chat、review、notes 通过公开 acquire 方法读取，不在多处赋值 container.chat_agent/container.retrieval 导致短暂不一致。

允许 AppContainer 提供只读兼容属性供已有代码使用，但生产请求必须捕获一次快照并在整个操作内使用。历史数据库、FileNoteRepository、DraftStore 沿用同一实例，不能每次切模型新建会话存储。

聊天激活：解析候选 → 实际探针验证 → 通过统一装配函数构造新 Agent（含新 budget 与同一 retrieval）→ 在短发布锁内核对 revision → 原子写 settings → 替换快照。候选构造/持久化失败保持旧对象；并发请求冲突返回 409。正在进行的请求继续持有旧快照至 finally 释放。

context_window 随 profile 保存，用现有 ContextBudget 逻辑生成 budget；不要依据模型名猜容量。默认沿用当前配置且让用户可编辑。Judge 配置保持独立，不因聊天选择而被无意覆盖。

### 5.2 向量切换与重建

采用适合当前小型单进程项目的串行维护窗口，避免一开始做双写/增量追赶：

1. 在同一门禁锁内检查 active chat/write 操作计数为 0 且无模型变更，再设置 maintenance=true；检查与设置必须原子，不能留竞态。
2. 创建并持久化 job 状态，202 返回。后台线程加载选中的本地模型（local_files_only=true），构造固定当前 chunk 配置的新 retrieval 和全新 collection。
3. 重用仓库路径校验和索引目标过滤，逐篇索引并更新进度；跳过 README、备份及原规则排除的文件。笔记集合为空也能成功建立有效空索引。
4. 构建前后检查笔记文件清单及内容 hash 一致；UI 写入已被门禁拦住，外部编辑检测到变化则本任务失败，保留旧索引并提示重试。
5. 按实际文件/chunk 数、指纹和至少一次非空语料检索检查候选；非空语料不得以零块成功。构造绑定新 retrieval 的完整 Agent/工具。
6. 原子持久化 active_embedding 与 revision，然后一次替换 RuntimeSnapshot；从此 chat/review/Documents 全部使用新索引。job succeeded 后清除 maintenance。
7. 失败或取消发布时保留旧 active 和对象，job failed，finally 解除门禁。不得删除旧 collection 或修改正式笔记。

维护期间拒绝 `/chat`、approve/override、所有 `/notes` 写操作（包括 folder rename/delete、move、手动 index）。拒绝发生在任何会话创建、消息写入、文件落盘、草稿消耗之前。reject 草稿可以保持可用，但要明确使用共享 DraftStore。前端 disabled 只是交互，后端门禁是必要保证。

维护期间也拒绝聊天 profile 保存/激活等配置变更，避免候选构建基于过期 profile；读取和不提交配置的连接测试可用。聊天验证请求结束后发布前再次检查 maintenance 和 revision，处理与重建启动同时发生的竞争。

每个写操作和聊天轮都在 try/finally 中释放占用；SSE 断开/异常也要释放。不要跨 await 持有普通 threading.Lock；计数/状态锁只覆盖短操作，阻塞模型加载与索引在 worker 线程执行。线程里的长期任务必须由 service 持有句柄、捕获异常，不用无法跟踪的 fire-and-forget。

重启时读取最后一次成功 active 指针；running job 标为 interrupted/failed，不能自动启用半成品。lifespan 退出时停止提交新任务，阻止被中断 job 发布，按受控方式等待/收尾。旧索引不会自动随新笔记更新，所以以后切回旧模型也要重新构建或验证完整语料 hash，不能简单切回过期 collection。

单进程限制写进部署说明。独立 CLI/外部程序不受内存门禁约束，说明维护期间不同时运行索引 CLI；多 worker 支持不是本期完成项。

## 6. 分步实施任务

### 任务 A：配置存储与模型工厂

**修改：** llm/factory.py、bootstrap/settings.py；新增 schemas.py、store.py 及对应单测。

- [x] 检查 git 状态及现有未提交更改，保留用户正在调整的 prompt 和文档。
- [x] 创建 profile 输入/公开输出/内部存储结构，写 API Key 不回显、保留旧 Key、原子写失败保持旧文件、revision 冲突测试。
- [x] 为 factory 增加独立函数 `create_chat_model_from_config(*, provider, model, base_url, api_key)`，保留 `create_chat_model(settings)` 和 `create_judge_model(...)` 的兼容契约。
- [x] 基于实际安装版本核对 init_chat_model 的 provider 参数和 base_url/api_base 转发；用 mock 断言 DeepSeek 和兼容服务各自使用正确参数，不只测对象类型。
- [x] 实现配置加载顺序：存在持久 active → 使用持久 active；不存在 → 从环境建立默认 profile。损坏的配置不能静默当作不存在覆盖，返回可诊断错误并保留原文件。
- [x] 为旧环境中的默认模型与当前 collection 生成初次状态，不直接把新代码默认值写进已有索引 metadata。

### 任务 B：本地向量候选列表

**新增：** catalog.py 和 test_model_catalog.py；复用 build_embedder。

- [x] 从配置缓存根列举支持的 MiniLM、bge-small-zh-v1.5、multilingual-e5-small；已知模型 id 和目录别名集中定义，不接受前端任意文件系统路径。
- [x] 检查 refs/snapshots 及必要配置、tokenizer、权重文件；候选状态使用 available/incomplete/unsupported，目录名存在不能直接标可用。
- [x] GET 列表不加载所有模型、不下载、不联网。真正切换时本地加载和一次编码验证，失败返回具体的可公开原因。
- [x] 用临时缓存目录覆盖完整、不完整、无缓存、非法 model_id 四类测试。当前 active 即使不可用也在状态中显示，不假装另一个模型已启用。

### 任务 C：运行管理器与跨模块连接

**新增：** service.py、必要的 bootstrap/runtime.py；**修改：** bootstrap/app.py、chat/router.py、notes/router.py。

- [x] 提取构建 ChatAgent 的唯一装配函数，复用 notes、history、drafts、prompt_path、budget。切换 embedding 时一起重建 tools；禁止修改 Agent 私有属性拼接新旧依赖。
- [x] 实现 RuntimeSnapshot、短发布锁、operation lease、维护门禁；请求成功获取 lease 才能创建会话或改笔记。
- [x] 对照 notes/router 全部写入口接门禁，review approve/override 同样接入。检查 folder move/rename/delete 引起的所有索引同步。
- [x] 实现聊天测试和激活事务，测试超时/认证失败/tool calling 不支持时状态不变。
- [x] 实现向量后台重建及进度、失败保留旧对象、重启中断恢复。CLI 与 UI 复用相同枚举过滤函数，不通过 subprocess 执行带用户参数的脚本。
- [x] 单测覆盖：一个旧聊天轮拿到 A 后激活 B，该轮所有调用仍用 A，下一轮用 B；retrieval 切换后 tools/review/Documents 全部用新对象；断连释放门禁；持久化失败不发布。
- [x] 集成测试使用临时笔记、临时 Chroma、fake embedder 验证真实索引路径。测试加载失败、中途某篇失败、空语料成功、外部修改失败、多标签页同时提交返回 409。

### 任务 D：HTTP 路由与错误映射

**新增：** router.py、tests/integration/test_model_settings_api.py；**修改：** bootstrap/app.py。

- [x] 按第 4 节实现接口，独立 router 注册在 create_app；API 不泄露 SecretStr 字段或内部配置 dump。
- [x] 参数验证错误也需脱敏：FastAPI/Pydantic 错误可能包含原始 input，涉及 Key 的 body 不得原样进入 422 响应或请求日志。
- [x] 对 activate/switch 接口核对 expected_revision，防止旧标签页覆盖新选择；409 响应指导重新获取配置。
- [x] 向量状态区分 active_model 与 target_model；202 不代表已切换，succeeded 前始终报告原模型生效。
- [x] 测试维护窗口内聊天返回 409 且消息数不增加、笔记写入无副作用；同时 GET 状态/笔记仍可用。
- [x] 本地无登录应用的敏感设置写接口沿用同源调用，拒绝不匹配的 Origin，不启用任意站点 CORS；服务端测试/CLI 没有 Origin 的行为明确记录。

### 任务 E：输入框下方右侧 UI

**修改：** home.html；**新增：** model-settings.js / .css；**修改：** create_app 静态路由。

- [x] 在现有 input-area 中、input-inner 后新增 model toolbar，使用 flex 与 justify-content:flex-end，窄屏可换行；保持 textarea、发送按钮、Enter/Shift+Enter 行为。
- [x] 聊天弹层展示 profile、添加/编辑表单；Key 使用 password 输入，测试/保存有 loading/error，返回结果使用 textContent，禁止把供应商字符串拼进 innerHTML。
- [x] 新增自定义聊天 profile 可以直接“保存并启用”，无需用户先保存再另点列表；已有项单击选择也走验证事务。成功后以服务端返回名称更新按钮。
- [x] 向量弹层只显示服务端候选；当前项标记已启用，不完整项禁用并展示原因；点击重建后显示阶段与文件进度。
- [x] job 运行中每 1 秒轮询；结束、页面卸载或视图退出停止高频轮询。刷新页面通过 GET /model-settings 恢复当前任务展示；失败显示旧模型仍启用。
- [x] 暴露小型前端接口 `ModelSettings.init()`、`ModelSettings.setStreaming(boolean)`、`ModelSettings.canSend()`，与现有 isStreaming 配合；维护期间更新发送/审批/文档写按钮状态，不能用一个布尔值覆盖已有空输入和 dirty 状态判断。
- [x] 多标签页在 focus、发送前、保存前刷新状态；后端 409 时保留用户输入与未保存正文。现有 send 先清 textarea，需在服务器拒绝时恢复该次输入，同时不覆盖用户随后输入的新文字。
- [x] 支持 Escape 关闭、外部点击关闭、焦点回到触发按钮、表单 label、键盘选择；长模型名省略显示但可查看全名。功能区只属于 Chat 输入栏，不挤占 Documents 编辑器。

### 任务 F：部署、测试和文档

**修改：** docker-compose.yml、.env.example、相关模块 README、docs/architecture/frontend.md、retrieval.md、scripts/README.md。

- [x] Compose 添加专用 model_settings 数据卷映射 `/app/var/model_settings`，不要覆盖整个 `/app/var` 隐藏镜像预下载模型。
- [x] 模型列表基于当前进程可见缓存。文档给出可选的缓存挂载方式；Windows 宿主下载的模型不会因目录存在自动出现在容器中。
- [x] 原生本地运行与 Docker 启动均加载持久 active。启动时核对 active collection 指纹；不匹配显示可修复状态而不隐式清库。若需要允许 UI 在 RAG 不可用时启动，将检索接口显式置为 unavailable，不能伪造空结果；允许选择模型重建恢复。
- [x] CLI 默认索引操作读取与 UI 相同的 active_embedding 配置解析函数，避免 UI 切到新 collection 而 CLI 更新旧库；评测脚本显式隔离配置，不能意外加载用户 active 或 Key。
- [x] 文档说明全局选择、Key 本地存储、后续请求生效、向量维护窗口、失败回退、单 worker 限制、配置优先级。
- [x] 记录本次变更涉及文件与验证结果。提交仅包含任务文件，不提交本地凭据、下载模型、生产笔记/向量库或用户既有改动。

## 7. 验证要求

下面为执行阶段命令，计划编写阶段不运行。按现有测试 fixture 规范构造隔离数据库/文件；不能依赖真实凭据通过单测。

```powershell
uv run pytest tests/unit/test_model_settings_store.py tests/unit/test_model_catalog.py tests/unit/test_model_management.py tests/unit/test_llm_factory.py tests/unit/test_app_container.py -q
uv run pytest tests/integration/test_model_settings_api.py tests/integration/test_notes_api.py tests/integration/test_retrieval_service.py tests/unit/test_chat_tools.py tests/unit/test_chat_agent_context.py tests/unit/test_drafts.py tests/unit/test_citations.py -q
```

针对凭据脱敏的测试需覆盖嵌套错误响应，不能只断言 GET 响应顶层没有 api_key：

```python
def test_invalid_profile_never_echoes_secret(client):
    marker = "test-only-secret-do-not-echo"
    response = client.post("/model-settings/chat/test", json={
        "label": "invalid", "provider": "unsupported", "model": "demo",
        "base_url": "https://example.invalid", "api_key": marker,
        "context_window": 32768,
    })
    assert response.status_code == 422
    assert marker not in response.text
```

必须在浏览器完成以下验收并记录截图/结果，不能只检查 HTML 包含按钮：

1. 桌面和窄屏下两个入口位于输入框下侧靠右，展开不遮挡输入、发送和引用面板。
2. 新增兼容服务配置，测试成功，启用后下一次聊天实际使用目标 model/base_url；Key 不出现在网络响应、浏览器持久存储或日志。
3. 错误 Key、无效 URL、服务不支持工具调用、请求超时均保留原 active，错误可读，表单可继续修改。
4. 选择另一个已下载 embedding，显示重建进度；过程中发送/写笔记被禁用且后端也拒绝；成功后历史检索、草稿批准、Documents 保存均操作新索引。
5. 注入重建失败，旧检索仍可用；刷新能恢复 job 结果；重启不启用未完成索引。
6. 保留已有 pending draft，切聊天模型和向量模型后继续批准/拒绝，笔记及索引行为正确。
7. 两标签页同时切换、SSE 中断、请求结束后再切换，不能卡死门禁或让界面误报成功。
8. 没有任何可用候选/当前索引已不兼容时，页面仍能展示真实状态并提供恢复入口。

真实联网验证只使用用户明确配置的服务和小型探针，不触发大规模 RAG 评测。缺少服务或浏览器能力时报告未完成项，不用 mock 结果宣称真实切换已验证。

## 8. Claude Code 执行指令

```text
请执行 docs/plans/2026-09-25-model-switching-ui.md，实现输入框下方靠右的聊天模型与向量模型切换。
先阅读 CLAUDE.md 与计划列出的调用链，保留已有未提交修改。
沿用原生前端与 LangChain；聊天支持 model/Base URL/API Key，向量只选择本地已有且受支持的模型。
按任务 A–F 实现，关注模型工厂、Agent 工具闭包、Documents、草稿审批、持久化和索引配置的一致性。
使用独立 collection 重建向量索引，成功后统一切换，失败保留原配置；不得删除旧索引或修改用户正式笔记。
遵循现有代码风格、类型与注释约定；职责分离、公开接口、必要操作日志，不增加无关重构或平台化组件。
完成计划测试与浏览器交互验收，最终说明改动、验证结果、未完成项和使用方式。
```

## 9. 执行结果（2026-09-25 实施）

### 9.1 测试

`uv run pytest tests -q` → **423 passed, 1 failed**。唯一失败是既有的 `tests/unit/test_system_prompt_learning_notes.py::test_v9_archive_is_byte_identical_to_production_prompt`：工作区里未提交的 v10 prompt 改动让 `system.txt` 与 v9 归档不再逐字节相同。与本功能无关，按要求保留、未改动。

新增/扩展的测试（全部通过）：

| 文件 | 数量 | 覆盖重点 |
|------|------|----------|
| `tests/unit/test_model_settings_store.py` | 19 | 加载顺序、原子写、revision 冲突、凭据不落盘、corrupt 诊断、URL/provider 规则 |
| `tests/unit/test_model_catalog.py` | 18 | 完整/不完整/无缓存/别名/非法 id、active 不在清单时仍显示 |
| `tests/unit/test_model_management.py` | 27 | 租约与门禁、激活事务、重建发布/失败回退/中断、真实 RetrievalService + 真实 Chroma 的重建 |
| `tests/integration/test_model_settings_api.py` | 21 | 8 个接口、脱敏、409、维护窗口、同源校验 |
| `tests/unit/test_llm_factory.py` | 6 | 旧契约不变 + `create_chat_model_from_config` 参数转发 |

### 9.2 浏览器验收

用一个隔离实例（SQLite + 临时 notes / chroma / model_settings，模型缓存只读复用）在浏览器完成。**未使用 mock 宣称真实切换。**

| # | 结果 | 说明 |
|---|------|------|
| 1 | ✅ | 两个入口位于输入框下侧靠右，窄屏换行；弹层向上展开在输入区之上，不遮挡输入框 / 发送按钮 / 引用面板；Documents 视图无工具栏 |
| 2 | ⚠️ 部分 | 表单、测试连接、错误提示、Key 不出现在响应与 DOM 均已验证；**"测试成功并启用真实服务"未验证**：本机没有可用的兼容服务（无 ollama、无 LM Studio、1234 端口关闭） |
| 3 | ✅ | 连不通时 502 + 可读原因，表单内容保留，原 active 不变 |
| 4 | ✅ | 真实切换：MiniLM → e5-small、→ bge-small-zh 各成功一次；进度按阶段显示，维护窗口内发送/写入禁用且显示提示、后端 409，完成后自动恢复 |
| 5 | ✅ | 重启后加载持久化的 e5 + 专属 collection + 真实指纹，`retrieval_available=true` |
| 6 | ⚠️ 未验证 | 保留 pending draft 跨切换继续审批：需要真实模型产出草稿 |
| 7 | ⚠️ 部分 | 两标签页 409 与租约释放有测试覆盖；SSE 中断未在浏览器手工验证 |
| 8 | ✅ | 候选状态区分 available/incomplete/unsupported 并给原因；active 不可用也照常显示；索引不可用时启动不崩，`retrieval_problem` 在向量弹层显示 |

浏览器验证期间发现并修复了三个假替身/单测没抓到的真实缺陷：

1. `RetrievalService` 缺 `indexed_files()` → 重建在清理幽灵片段时 `AttributeError`。已补方法，并新增"真实 RetrievalService + 真实 Chroma"的重建测试防止回归。
2. 前端在维护窗口内没有及时进入 busy 状态（发送按钮仍可点）→ 切换返回 202 后立即置 `busy` 并刷新按钮状态。
3. 弹层锚在按钮上，向上展开会盖住输入框 → 改为锚定整个 `.input-area`。

### 9.3 变更文件

新增：`src/noteagent/model_management/{__init__,schemas,store,catalog,service,router}.py` 与 `README.md`、`src/noteagent/bootstrap/runtime.py`、`src/noteagent/web/static/model-settings.{js,css}`、上表 4 个测试文件。

修改：`bootstrap/{app,settings}.py`、`llm/{factory.py,__init__.py}`、`chat/{router,tools}.py`、`notes/router.py`、`retrieval/{service,vector_store}.py`、`scripts/index_notes.py`、`web/{__init__.py,templates/home.html,README.md,static/README.md}`、`tests/unit/test_llm_factory.py`、`tests/integration/{test_app,test_notes_api}.py`、`docker-compose.yml`、`.env.example`、`docs/architecture/{frontend,retrieval}.md`、`scripts/README.md`。

### 9.4 未完成项

- 真实供应商的成功激活（见上表第 2 条）。
- Docker 未构建运行（本机 Docker daemon 未启动）：compose 卷与文档已按计划改好，镜像内候选列表行为未实机验证。
- 多标签页与 SSE 中断的浏览器手工验证。
- 单 worker 限制只写进文档，未做多 worker 支持（计划内不做）。

