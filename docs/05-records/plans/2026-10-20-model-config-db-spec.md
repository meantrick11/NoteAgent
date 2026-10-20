# 模型配置模块规范（Spec）

> 本文是 2026-10-20 模型模块重构的实现基线，对应上层 [ADR-003](../../../NoteAgent-docs/docs/03-architecture/ADR/ADR-003-模型配置数据库化与通用Provider.md)、[CR-2026-006](../../../NoteAgent-docs/docs/09-decisions/CR-2026-006-模型配置数据库化与通用Provider.md)、[MOD-007](../../../NoteAgent-docs/docs/04-modules/MOD-007-模型配置与运行对象管理.md)、[API-004](../../../NoteAgent-docs/docs/05-interfaces/API-004-模型配置与索引切换契约.md)、[DATA-002](../../../NoteAgent-docs/docs/06-data/DATA-002-业务对象与权威存储.md)。实现状态以结果文档与测试证据为准，规范成立不等于功能已验收。

| 项 | 值 |
|---|---|
| Spec ID | SPEC-MODEL-CONFIG-001 |
| 状态 | Implemented（真实 Provider/生产迁移待验收） |
| 范围 | NoteAgent 模型配置、Provider 抽象、能力验证、激活与运行选择、配置迁移 |
| 不包含 | RAG 切片/embedding 检索策略、角色路由、多用户/租户、任意协议透传 |
| 适用形态 | 本地单用户部署（当前唯一形态） |
| 上位文档 | MOD-007、API-004、DATA-002、ARC-003/005/007、MOD-009/011、REQ-001/010/012/013/014 |
| 规范用语 | 必须 / 应当 / 可以 对应 MUST / SHOULD / MAY |

## 1. 背景与问题

模型模块当前把连接信息、模型信息、能力标签、运行选择、embedding 状态全部存于 `var/model_settings/settings.json`；`.env` 同时承担 `CHAT_MODEL`、`JUDGE_MODEL`、`DEEPSEEK_API_KEY` 等模型配置。由此产生：

- 配置边界不清：模型、检索、部署参数混在一个文件和一组环境变量里。
- 多模型支持弱：只有一个全局 active，候选配置与连接信息无法清晰复用。
- 能力语义分散：`capabilities`、`verified_capabilities`、`text_enabled` 三处共同表达“声明/验证/启用”。
- Provider 规则写死：领域校验包含 DeepSeek 专属限制，新增供应商需要改契约。
- 视觉解析旁路：解析前重新读取配置文件，与运行快照存在双读风险。

本规范定义目标模型模块的外部行为与数据契约，作为实现与验收的基线。

## 2. 目标与非目标

### 2.1 目标

- G-1 支持保存多个模型配置，全局最多一个 active；启用走“测试 → 构造 → 原子发布”。
- G-2 提供通用 Provider 抽象，领域契约不写死具体供应商。
- G-3 能力使用结构化记录，能表达启用、验证、来源、时间、探针版本与证据。
- G-4 模型配置以 PostgreSQL 为权威，领域层通过仓储端口与存储解耦。
- G-5 模型配置与 Retrieval/embedding 配置边界清晰，各自拥有 revision 与 API。
- G-6 移除 `.env` 中的模型配置；保留一次性迁移路径。
- G-7 保留现有可靠性语义：revision CAS、两阶段激活、请求级快照、失败保留旧模型。
- G-8 视觉解析使用上传时固定的模型身份，配置变化可检测、可重试。

### 2.2 非目标

- NG-1 不引入 chat/judge/vision 角色绑定或用途路由。
- NG-2 不提供会话级模型选择；模型选择不进入会话历史与回退。
- NG-3 不拆分独立连接表；同一 Key 配多个模型时允许重复填写。
- NG-4 不实现多用户、user_id、RBAC、租户隔离。
- NG-5 不改变 RAG 的切片、索引重建、collection 指纹与检索算法。
- NG-6 不支持未安装 SDK 的任意协议透传。
- NG-7 本轮不做应用层密钥加密。

## 3. 术语与领域模型

| 术语 | 定义 |
|---|---|
| ModelConfig | 一条模型配置：Provider、端点、凭据、上游模型名、参数、是否 active、行级 revision |
| CapabilityRecord | 某模型某能力的结构化记录：status、verification、source、checked_at、probe_version、evidence |
| ProviderSpec | 代码内注册的 Provider 适配器规格：id、显示名、LangChain provider、默认端点、端点是否必填、允许的认证方式 |
| Active Model | 当前进入运行快照的唯一模型；`is_active=true` 至多一行 |
| Model Revision | 单个模型行的配置修订号；所有写操作必须 CAS |
| Retrieval Revision | embedding/索引配置自己的修订号，与模型行 revision 独立 |
| RuntimeSnapshot | 一次请求固定的运行对象集合：active 模型、ChatAgent、检索对象、embedding 身份 |

领域不变量：

- DOM-1 任意时刻 active 模型数为 0 或 1。
- DOM-2 模型 id 创建后不可变。
- DOM-3 active 模型必须存在 `text` 能力行且 `status=enabled`、`verification=verified`。
- DOM-4 能力记录以 `(model_id, capability)` 唯一。
- DOM-5 ModelConfig 的 Provider 必须存在于 Provider 注册表。

## 4. 数据模型

### 4.1 `model_configs`

| 字段 | 类型 | 约束 |
|---|---|---|
| id | String(64) | PK；创建后不可变 |
| label | Text | NOT NULL；用户可见名称 |
| provider | String(32) | NOT NULL；`ProviderSpec.id` |
| model | Text | NOT NULL；上游模型名 |
| base_url | Text | NOT NULL default ''；是否必填由 ProviderSpec 决定 |
| auth_mode | String(16) | NOT NULL default 'api_key'；允许值由 ProviderSpec 决定 |
| api_key | Text | NOT NULL default ''；不得出现在任何 HTTP 响应或日志 |
| timeout_s | Integer | NOT NULL default 60 |
| max_retries | Integer | NOT NULL default 1 |
| context_window | Integer | NOT NULL default 32768；必须为正 |
| temperature | Float | NULL；NULL 表示交给 Provider |
| max_tokens | Integer | NULL；NULL 表示交给 Provider |
| is_active | Boolean | NOT NULL default false |
| revision | Integer | NOT NULL default 1 |
| created_at / updated_at | timestamptz | NOT NULL |

约束：

- DB-1 必须存在部分唯一索引：`UNIQUE (is_active) WHERE is_active`，保证 active 至多一行。
- DB-2 active 行不得删除；删除非 active 行时能力行必须级联删除。
- DB-3 同一 Provider 下允许同一上游模型名存在多行（以 label 区分）。
- DB-4 所有写操作必须使用 `WHERE id=:id AND revision=:expected`，成功后 revision +1；0 行影响即冲突。
- DB-5 不得为模型配置新增通用 JSON/blob 配置列；Provider 专属扩展在出现真实需求后另立规范。

### 4.2 `model_capabilities`

| 字段 | 类型 | 约束 |
|---|---|---|
| model_id | FK → model_configs | ON DELETE CASCADE；联合主键 |
| capability | String(32) | 联合主键；见 4.3 |
| status | String(16) | `enabled` / `disabled` |
| verification | String(16) | `unverified` / `verified` / `failed` |
| source | String(16) | `manual` / `probe` |
| checked_at | timestamptz | NULL |
| probe_version | Integer | NULL；与当前探针常量不一致视为需重验 |
| evidence | JSONB | NULL；只允许脱敏证据 |
| updated_at | timestamptz | NOT NULL |

### 4.3 能力枚举

- 本期允许落行：`text`、`vision`。
- `tool_calling`、`streaming`：作为 `text.evidence` 的子检查，不单独落行。
- `json_mode`、`reasoning`：仅保留枚举位，不实现探针、不暴露 UI。

## 5. Provider 规范

- PRV-1 领域与 Service 必须通过 Provider 注册表解析 Provider；不得出现按供应商名称分支的规则。
- PRV-2 `ProviderSpec` 至少包含：`id`、`label`、`langchain_provider`、`default_base_url`、`base_url_required`、`auth_modes`。
- PRV-3 内置适配器必须覆盖当前已安装 SDK：`deepseek`、`openai`、`openai-compatible`。
- PRV-4 Provider 校验必须由规格驱动：未知 provider 拒绝；`base_url_required=true` 时缺失拒绝；`auth_mode` 不在 `auth_modes` 时拒绝。
- PRV-5 客户端构造必须统一走 `init_chat_model(model, model_provider, base_url?, api_key?)`，不按供应商写 if/else。
- PRV-6 新增 Provider 必须满足：安装对应 LangChain 集成包 + 注册 `ProviderSpec` + 增加规格测试；不需要数据库迁移或领域契约变更。
- PRV-7 前端 Provider 下拉必须由 `GET /model-settings/providers` 驱动，不得维护硬编码联合类型。

## 6. 能力验证状态机

### 6.1 初始状态

- CAP-1 创建模型时必须插入 `text` 能力行：`status=enabled`、`verification=unverified`、`source=manual`。
- CAP-2 `vision` 行在首次验证时创建；未验证时不要求存在。

### 6.2 验证

- CAP-3 `text` 验证必须执行流式输出与工具调用两项探测；两项均通过才可写 `verification=verified`，`evidence` 至少包含 `{"streaming": bool, "tool_calling": bool}`、`checked_at`、当前 `probe_version`；失败写 `failed`。
- CAP-4 `vision` 验证必须先通过 `text` 探测，再执行两轮独立图片挑战；通过后 upsert `vision` 行为 `status=enabled`、`verification=verified`，同时写证据、时间、版本。
- CAP-5 验证写入必须携带该模型行 `expected_revision`；探测期间配置变化 → 409，不得写入旧证据。

### 6.3 停用与失效

- CAP-6 停用 `text`：`status=disabled`，保留 `verification` 与证据；聊天租约必须拒绝新请求。
- CAP-7 停用 `vision`：`status=disabled`，同时清空 `verification/evidence/checked_at/probe_version`；重新启用必须重新验证（保持当前“删除后需重验”的用户预期）。
- CAP-8 修改 Provider、base_url、api_key、上游模型名时，必须在同一事务中把该模型全部能力重置为 `unverified` 并清空验证字段，保留 `status`。
- CAP-9 `probe_version` 与当前常量不一致时，读取侧必须视为未验证；探针逻辑变化必须升级版本常量。
- CAP-10 聊天准入必须同时满足：active 模型存在、`text.status=enabled`、`text.verification=verified`、`probe_version` 有效。
- CAP-11 视觉解析准入必须同时满足：`vision.status=enabled`、`verification=verified`、`probe_version` 有效。

## 7. 运行行为

### 7.1 启动

- RUN-1 启动必须依次执行：数据库迁移 → 遗留配置导入（如适用）→ 加载 active 模型与能力 → 装配快照。
- RUN-2 无 active 模型时必须正常启动，设置页可用；聊天接口在 SSE 开始前返回 503 `MODEL_NOT_CONFIGURED`。
- RUN-3 active 模型存在但不可用（缺 Key、客户端构造失败等）时必须 fail-fast，错误信息必须指出模型与修复方式；不得静默换模型。

### 7.2 聊天

- RUN-4 `chat` 租约必须在整个请求内固定同一 `RuntimeSnapshot`；工具闭包、检索对象、模型客户端不得在轮内变化。
- RUN-5 聊天准入按 CAP-10 执行；已在执行的请求不受后续停用影响。

### 7.3 激活

- RUN-6 激活必须两阶段：锁外完成 Provider 校验、能力校验、探测、客户端与 Agent 构造；锁内/事务内复核 revision 并切换 active。
- RUN-7 激活事务必须锁定目标行与旧 active 行，核对目标行 revision；成功后目标行 `is_active=true` 且 revision +1，旧 active 行仅置 `is_active=false`（不递增 revision）。
- RUN-8 激活任何一步失败必须保留旧 active、旧 revision 与旧快照。
- RUN-9 active 行不得通过普通 PUT 修改；必须通过带完整配置的激活请求完成“保存并启用”，避免配置与运行客户端漂移。

### 7.4 能力变更与快照

- RUN-10 能力验证/停用必须递增该模型行 revision；若该模型为 active，必须同步更新快照中的 revision 与能力摘要，不重建 Agent。
- RUN-11 停用 active 模型的 `text` 后，新聊天必须立即被拒绝；视觉能力状态独立变化。

### 7.5 删除

- RUN-12 active 模型不得删除。
- RUN-13 非 active 模型可删除；能力行级联删除；已被来源文件固定的模型删除后，相关解析必须明确失败（与当前删除 profile 的行为一致）。

### 7.6 视觉与上传

- RUN-14 上传/重试时必须记录当时 active 模型的 `model id` 与该行 `revision`；现有 `parse_profile_id/parse_profile_revision` 列名可以沿用，但语义必须是 model id/row revision。
- RUN-15 视觉解析必须按固定 model id 读取模型与能力行，不得读取旧 JSON 配置；必须校验该行 revision、vision 能力、probe_version。
- RUN-16 解析期间 active 切换到其他模型不得改变已固定来源的解析身份；固定模型配置变化或删除时必须报错并要求重试。
- RUN-17 上传时 active 模型无已验证 vision：图片解析必须失败；无文本 PDF 保持现有回退行为。

### 7.7 并发与单进程约束

- RUN-18 运行快照发布锁仅在进程内有效；当前形态为单 worker，不承诺跨进程快照失效通知。
- RUN-19 数据库层必须提供行级 CAS；不得依赖进程内锁保证配置一致性。

## 8. Revision 与配置边界

- REV-1 模型配置使用行级 revision；不得再用一个全局 revision 覆盖所有模型写入。
- REV-2 Embedding/检索必须使用自己的 revision；模型模块不得读写 embedding 状态。
- REV-3 设置页聚合接口可以同时返回模型与 embedding，但不得返回被前端当作“全局 revision”使用的单一字段。
- REV-4 前端必须按域维护 revision：模型 store 与检索 store 独立，互不覆盖。
- REV-5 embedding 端点可以暂时保留原路径，但实现必须归属 Retrieval；Models 模块不得继续拥有 `active_embedding/embedding_job` 的读写逻辑。

## 9. 配置边界与 `.env`

- ENV-1 `.env` 必须只保留基础/引导配置：`DATABASE_URL`、`HOST`/`PORT`、`NOTES_DIR`、`NOTES_HISTORY_DIR`、`CHROMA_DIR`、`UPLOADS_DIR`、`LOG_DIR`/`LOG_LEVEL`、`FRONTEND_MODE`，以及 Retrieval 现有 `EMBEDDING_*`/`CHUNK_*`。
- ENV-2 `.env` 必须删除：`DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`、`CHAT_MODEL`、`JUDGE_MODEL`、`CHAT_CONTEXT_WINDOW`。
- ENV-3 `MODEL_SETTINGS_DIR` 只可以作为遗留导入路径保留一个发布周期，不得作为模型配置权威。
- ENV-4 脚本/评测必须通过仓储解析 active 模型；可以保留显式 CLI 模型参数作为离线覆盖，但不得依赖模型相关环境变量。
- ENV-5 离线脚本使用仓储时依赖 `DATABASE_URL`，文档必须明确这一点。

## 10. HTTP 接口规范

前缀保留 `/model-settings`。所有写操作必须携带行级 `expected_revision`（新建除外）。响应不得包含 `api_key`，只暴露 `has_api_key`。

| 接口 | 行为 | 关键规则 |
|---|---|---|
| `GET /model-settings` | 返回模型列表、active、embedding 聚合信息 | 每个模型带 `revision`、`is_active`、`capabilities` 行；不返回单一全局 revision |
| `GET /model-settings/providers` | 返回 ProviderSpec 列表 | 前端据此渲染 provider、base_url 必填、auth_mode |
| `POST /model-settings/models` | 新建模型 | 自动创建 `text` 能力行；Provider 规格校验 |
| `PUT /model-settings/models/{id}` | 修改非 active 模型 | 行级 CAS；连接字段变化重置能力验证 |
| `DELETE /model-settings/models/{id}` | 删除非 active 模型 | active 拒绝；能力级联删除 |
| `POST /model-settings/models/{id}/test` | 测试已保存模型 | 不保存、不激活 |
| `POST /model-settings/models/{id}/activate` | 激活；可携带完整 `config` | 行级 CAS；两阶段提交；失败保留旧 active |
| `POST /model-settings/models/{id}/capabilities/{capability}/verify` | 验证能力 | 行级 CAS；探测期间变化返回 409 |
| `DELETE /model-settings/models/{id}/capabilities/{capability}` | 停用能力 | text 保留验证；vision 清空验证 |
| embedding 端点 | 暂保留 | 由 Retrieval 实现与 revision 管理 |

错误规范：

- API-1 未知 Provider、规格不满足、能力不满足：4xx + 可读原因。
- API-2 revision 冲突：409，客户端必须刷新后重提。
- API-3 无 active 模型时聊天：503 `MODEL_NOT_CONFIGURED`，设置页仍可用。
- API-4 凭据空字符串必须解释为“保持原值”；清除必须显式 `clear_api_key`。
- API-5 旧 `/chat/profiles*` 端点在新前端上线后删除，不做长期双轨兼容。

## 11. 前端规范

- UI-1 “模型与连接”必须展示模型列表、active 标记、能力徽章，并支持新建/编辑/删除/启用。
- UI-2 Provider 下拉与 Base URL 必填规则必须来自 `GET /providers`。
- UI-3 能力徽章必须可验证/停用，并展示最近验证时间；停用 vision 后再次启用必须重新验证。
- UI-4 快捷面板只显示 active 模型并支持切换；切换必须走测试 + 激活。
- UI-5 表单必须包含 label、provider、model、base_url、auth_mode、api_key（keep/set/clear）、context_window、temperature、max_tokens、timeout/retries。
- UI-6 模型 store 与检索 store 必须独立持有 revision；设置页只组合两块，不得互相覆盖基线。
- UI-7 embedding 区域功能保持不变，只迁移归属。

## 12. 迁移规范

- MIG-1 必须通过 Alembic 创建两张表；迁移文件使用描述性 PascalCase 名称。
- MIG-2 启动时必须执行幂等导入：表为空且旧 `settings.json` 存在时，每个 `ChatProfile` 导入为一行 ModelConfig + 能力行；`active_chat_profile_id` 映射为 `is_active`。
- MIG-3 `credential_source=env` 的行必须在导入时解析当时 `.env` 的 Key 并写入数据库；日志只记录数量，不打印 Key。
- MIG-4 导入前必须复制 `settings.pre-db.json`（0600）；导入后 `settings.json` 只保留 embedding 字段供 Retrieval 读取，聊天配置字段清空。
- MIG-5 无旧文件且表为空时必须进入“未配置”启动态，不得自动生成默认模型。
- MIG-6 回滚必须支持：停服 → `alembic downgrade` → 恢复 `settings.pre-db.json` 为 `settings.json` → 回退代码。
- MIG-7 embedding 状态本轮不迁移；只做边界读取，不改检索逻辑。

## 13. 非功能要求

- NFR-1 安全：`api_key` 不得出现在 HTTP 响应、错误信息、日志与前端状态；数据库备份包含凭据，备份/恢复文档必须提示。
- NFR-2 可靠性：任何激活/验证失败不得改变旧 active、旧快照或旧 revision；错误必须用户可见。
- NFR-3 可观测：配置创建/修改/删除、能力验证结果、激活成功/失败、遗留导入数量必须记录日志；不得记录密钥。
- NFR-4 性能：聊天路径不得增加额外探测请求；激活探测沿用现有 20 秒上限；配置查询为小表全量读取。
- NFR-5 兼容：API 为破坏性变更，前后端必须同版本发布；旧端点不长期保留。
- NFR-6 可测试：能力状态机、Provider 规格、行级 CAS、导入器必须有确定性单测；数据库行为必须有集成测试；真实 Provider 探测单独记录，不得用模拟结果冒充验收。

## 14. 代码组织与解耦规范

### 14.1 分层职责

| 层 | 位置 | 职责 | 禁止 |
|---|---|---|---|
| Domain | `Domain/Vo` | 实体、值对象、能力状态机、Provider 规格值对象、仓储端口、错误类型 | 不得 import SQLAlchemy、FastAPI、LangChain、文件/网络 |
| DTO | `Domain/Dto` | HTTP 请求/响应模型 | 不得 import ORM 或 Mapper |
| Po | `Domain/Po` | SQLAlchemy ORM 映射 | 不得包含业务规则 |
| Mapper | `Mapper` | 仓储实现、ORM↔领域转换、遗留 JSON 读取 | 不得处理 HTTP；不得编排业务流程 |
| Provider | `Provider` | Provider 注册表、客户端工厂、能力探针 | 不得访问数据库/HTTP 路由 |
| Service | `Service` | 配置用例、能力验证、激活、快照与租约 | 不得直接写 SQL/ORM；不得解析 HTTP |
| Router | `Router` | HTTP 适配、DTO 映射、错误转换 | 不得包含业务规则或 SQL |
| Bootstrap | `AppBootstrap` | 装配实现与端口注入 | 不得包含业务规则 |

### 14.2 目标文件结构（Models 模块）

```text
src/NoteAgent/Modules/Models/
  Domain/Vo/
    ModelConfig.py              # ModelConfig 聚合、参数、凭据合并与校验
    ModelCapabilities.py        # 能力枚举、记录、状态机（纯函数）
    ProviderSpec.py             # ProviderSpec 值对象
    ModelRepository.py          # ModelRepositoryPort
    ModelErrors.py
  Domain/Dto/ModelSettingsSchemas.py
  Domain/Po/ModelConfigModels.py
  Mapper/
    SqlModelConfigRepository.py # 事务、行级 CAS、active 唯一、能力读写
    ModelConfigMappers.py       # ORM ↔ 领域对象
    LegacyModelSettingsReader.py# 只读旧 JSON
  Provider/
    ProviderRegistry.py         # 内置规格 + ProviderCatalogPort 实现
    ModelClients.py             # 统一客户端工厂
    ModelProbes.py              # text/vision 探针与版本常量
  Service/
    ModelPorts.py               # AgentAssemblerPort、ChatAgentPort、RetrievalPort
    ModelConfigService.py       # CRUD、Provider 校验、能力验证/停用、测试
    ModelActivationService.py   # 激活编排：验证→构造 Agent→提交→发布
    ModelRuntimeService.py      # 快照、租约、状态、publish；不写配置
    LegacyModelSettingsImporter.py
  Router/ModelSettingsRoutes.py # 薄路由
```

Retrieval 边界（目标归属，算法不变）：

```text
src/NoteAgent/Modules/Retrieval/
  Service/EmbeddingSettingsService.py   # embedding 候选、切换、任务、状态
  Router/RetrievalSettingsRoutes.py     # embedding 端点（路径可暂保留）
  Mapper/RetrievalStateStore.py         # 现有 embedding 状态的读写
```

### 14.3 服务边界与调用关系

| 服务 | 只负责 | 不负责 |
|---|---|---|
| `ModelConfigService` | 模型/能力的配置用例、Provider 规格校验、探测并写证据、`test`、`build_client_for_parse` | 构造 ChatAgent、发布快照、embedding |
| `ModelActivationService` | 激活编排：取候选→验证→构造 Agent→仓储激活→通知运行时发布 | CRUD 端点、快照租约、embedding |
| `ModelRuntimeService` | 持有当前 `RuntimeSnapshot`、read/write/chat 租约、`publish`、状态读取 | 直接写数据库、探测、embedding 重建 |

```text
Router ──> ModelConfigService ──> ModelRepositoryPort
                               ├─> ProviderCatalogPort
                               ├─> Provider/ModelClients + ModelProbes
Router ──> ModelActivationService ──> ModelConfigService
                                  ├─> AgentAssemblerPort
                                  ├─> ModelRepositoryPort.activate
                                  └─> ModelRuntimeService.publish
ChatRoutes ──> ModelRuntimeService（租约/快照）
SourceVision ──> ModelConfigService.build_client_for_parse(model_id, revision)
Bootstrap ──> 实例化 Mapper/Provider/服务并注入端口
```

### 14.4 端口（Protocol）

- `ModelRepositoryPort`：`list/get/get_active/create/update/delete/replace_capabilities/activate`。所有写入带 `expected_revision`；`activate` 在适配器内部完成锁定、切换 active、可选保存配置与能力、递增 revision 的事务。
- `ProviderCatalogPort`：`resolve(provider_id)` / `list_specs()`。
- `AgentAssemblerPort`：`build_agent(model, retrieval) -> ChatAgentPort`；由 Bootstrap 实现，Models 不 import Chat 具体类。
- `ChatAgentPort`：只声明 Models/Router 需要的最小方法（如 `stream`、`review`），避免 Models 依赖 Chat 内部结构。
- `RetrievalPort`：提供当前检索对象与状态；由 Retrieval 实现，Models 不 import Retrieval 内部类。

端口只放接口，不放实现；实现全部在 Mapper/Provider/Bootstrap。

### 14.5 依赖规则

- DEP-1 Domain 不得 import 任何框架/IO；只允许标准库与 Pydantic。
- DEP-2 Provider/Mapper 可以依赖 Domain；Domain 不得反向依赖它们。
- DEP-3 Service 可以依赖 Domain、端口、Provider 的纯函数；不得 import Mapper/ORM。
- DEP-4 Router 可以依赖 Service、DTO；不得 import Mapper/ORM。
- DEP-5 Bootstrap 依赖全部实现并负责注入；Models 不得 import `AppBootstrap`。
- DEP-6 Models 不得 import Retrieval 内部类；通过 `RetrievalPort` 交互。
- DEP-7 Models 不得 import Chat 具体类；通过 `ChatAgentPort`/`AgentAssemblerPort` 交互。
- DEP-8 前端 `features/models` 与 `features/retrieval` 不得互相 import；只在 `features/settings` 组合。
- DEP-9 只有 Bootstrap/AppSettings 读取环境变量；Models 业务代码不得读取 `.env`。

### 14.6 现有文件迁移

| 现有文件 | 目标 |
|---|---|
| `Domain/Vo/ModelContracts.py` | 拆为 `Domain/Vo/ModelConfig.py`（领域）与 `Domain/Dto/ModelSettingsSchemas.py`（HTTP） |
| `Domain/Vo/ModelProfiles.py` | 合并进 `ModelConfig.py`（凭据合并/校验规则） |
| `Domain/Vo/ModelCatalog.py` | 移到 Retrieval（embedding 候选目录） |
| `Mapper/ModelSettingsStorage.py` | 删除文件存储实现；保留 `LegacyModelSettingsReader` 一次性读取 |
| `Service/ModelRuntime.py` | 拆为 `ModelConfigService` + `ModelActivationService` + `ModelRuntimeService` |
| `Provider/ModelClients.py` | 拆出 `ProviderRegistry.py`；工厂不再按供应商分支 |
| `Provider/ModelProbes.py` | 保留，增加探针版本与证据结构 |
| `Router/ModelSettingsRoutes.py` | 重写；embedding 端点移交 Retrieval |
| `AppBootstrap/SourceVision.py` | 改为调用 `ModelConfigService.build_client_for_parse`，不读 JSON |
| `AppBootstrap/RuntimeAssembler.py` | 实现 `AgentAssemblerPort`；保留唯一装配入口 |

### 14.7 测试组织

- 单测：`Tests/Unit/Modules/Models/Domain/`（能力状态机）、`Provider/`（规格/工厂）、`Service/`（配置/激活，使用 Fake Repository）。
- 集成：`Tests/Integration/Models/`（仓储 CAS、active 唯一、事务回滚、遗留导入、HTTP）。
- 前端：按 `features/models` 与 `features/retrieval` 分目录；e2e 覆盖两个 revision 域。
- 架构测试：用 import 扫描/静态检查保证 DEP-1~DEP-9，防止解耦随时间退化。

### 14.8 禁止的模式

- Router 直接执行 SQL/ORM 查询。
- Mapper 处理 HTTP 或业务编排。
- Domain 依赖 SQLAlchemy/FastAPI/LangChain。
- `ModelRuntimeService` 同时承担 CRUD、探测与 embedding 重建。
- 前端 models 与 retrieval 互相 import。
- 业务代码读取 `.env` 中的模型配置。

## 15. 验收标准

| ID | Given / When / Then |
|---|---|
| AC-01 | Given 旧 `settings.json` 含 N 个 profile，When 首次启动导入，Then 数据库有 N 行模型与对应能力行，active 等价，旧文件已备份且聊天配置字段清空 |
| AC-02 | Given 已有 active 模型，When 激活另一个模型成功，Then 仅目标行 `is_active=true`，旧行变为 false，快照指向新模型 |
| AC-03 | Given 激活探测失败，When 提交激活，Then 返回可读错误，旧 active、旧 revision、旧快照保持不变 |
| AC-04 | Given 已保存模型，When 验证 text 成功，Then `text` 行为 verified 且 evidence 含流式/工具结果；When 停用 text，Then 新聊天被拒绝但验证结果保留 |
| AC-05 | Given text 验证通过，When 验证 vision 成功，Then vision 行为 enabled+verified；When 停用 vision，Then 验证字段被清空，重新启用必须重验 |
| AC-06 | Given 模型已验证，When 修改 Key/端点/上游模型名，Then 全部能力变为 unverified，active 模型的普通 PUT 被拒绝并提示“保存并启用” |
| AC-07 | Given 客户端持有旧 revision，When 提交修改/验证/激活，Then 返回 409，数据库不变 |
| AC-08 | Given 空数据库，When 启动，Then 应用可用、设置页可打开、聊天返回 503 `MODEL_NOT_CONFIGURED` |
| AC-09 | Given active 模型缺 Key，When 启动，Then 启动失败并指出模型与修复方式，不静默换模型 |
| AC-10 | Given 上传时 active 为模型 A，When 解析前 active 切到 B，Then 来源仍按 A 解析；When A 配置变化，Then 解析失败并要求重试 |
| AC-11 | Given 未知 Provider 或缺少必填 Base URL，When 保存模型，Then 拒绝并给出规格原因 |
| AC-12 | Given 任意响应/日志，When 检查，Then 不包含 `api_key` 明文 |
| AC-13 | Given 模型保存与 embedding 切换，When 两者交替使用旧 revision，Then 互不覆盖，各自返回自己的冲突 |
| AC-14 | Given active 模型，When 删除，Then 拒绝；Given 非 active 模型，When 删除，Then 能力行级联删除 |
| AC-15 | Given 规范更新，When 检查文档，Then 旧表述（JSON 权威、DeepSeek 专属规则、vision 仅声明、全局 revision）已清零 |
| AC-16 | Given Domain 层代码，When 运行 import 扫描，Then 不存在 SQLAlchemy/FastAPI/LangChain/文件/网络依赖（DEP-1） |
| AC-17 | Given Router/Mapper 代码，When 运行静态检查，Then Router 无 SQL/ORM、Mapper 无 HTTP/业务编排（DEP-4、14.8） |
| AC-18 | Given Models 模块，When 检查服务职责，Then CRUD、激活、快照分别位于 `ModelConfigService`、`ModelActivationService`、`ModelRuntimeService`，运行时服务无配置写入（14.3） |
| AC-19 | Given 前端代码，When 检查 import，Then `features/models` 与 `features/retrieval` 互不依赖，只由 `features/settings` 组合（DEP-8） |
| AC-20 | Given 旧实现文件，When 完成迁移，Then `ModelSettingsStorage` 文件存储与业务代码读取 settings.json 的路径已删除，仅遗留导入器可读旧文件（14.6） |

## 16. 需求追踪

| 需求 | 对应规范 |
|---|---|
| REQ-001 基础聊天 | RUN-4/5、CAP-10、NFR-4 |
| REQ-010 运行强健性 | RUN-2/3/6/7/8、REV-1/2、NFR-2/3 |
| REQ-012 前端设置 | UI-1~7、API-1~5 |
| REQ-013 文件输入 | RUN-14/16/17 |
| REQ-014 图片与 OCR | CAP-4/11、RUN-14~17 |
| REQ-004/008 检索 | REV-2/5、MIG-7（不改检索算法） |
| REQ-018 历史回退 | NG-2（模型选择不进入历史） |
| ARC-003 设置边界 | UI-1~7、G-1/2/3 |
| ARC-007 视觉链路 | CAP-4/11、RUN-14~17 |

## 17. 受影响文档（实现前必须同步）

- `NoteAgent-docs/docs/03-architecture/ADR/ADR-003-模型配置数据库化与通用Provider.md`（新建）
- `docs/04-modules/MOD-007-模型配置与运行对象管理.md`
- `docs/05-interfaces/API-004-模型配置与索引切换契约.md`
- `docs/06-data/DATA-002-业务对象与权威存储.md`
- `docs/03-architecture/ARC-003-设置与平台边界.md`、`ARC-005-系统分层与技术架构.md`、`ARC-007-聊天文件上传与笔记生成.md`
- `docs/04-modules/MOD-009-来源采集与材料整理.md`、`MOD-011-应用装配与部署生命周期.md`
- `docs/05-interfaces/API-005-来源任务与整理逻辑契约.md`
- `docs/07-quality/TC-001-全链路场景与模块验收.md`
- `docs/08-release-ops/OPS-003-部署备份与故障恢复.md`
- 仓库：`README.md`、`.env.example`、`docs/01-architecture/architecture.md`、`docs/04-ops/getting-started.md`

文档验收：删除“settings.json 是模型配置权威”“DeepSeek 专属规则”“vision 仅用户声明”“全局 revision”等旧表述；版本号、变更记录、上下游链接保持一致。

## 18. 已决事项与待决事项

已决：

- 存储：PostgreSQL 两表；仓储端口隔离。
- 选择：多配置、全局唯一 active；不做角色路由/会话级。
- 能力：结构化能力表；text/vision 本期落地。
- Provider：注册表驱动；内置 deepseek/openai/openai-compatible。
- 密钥：本轮明文入库，API 脱敏；加密留待多用户前。
- 视觉：上传时固定 model id + 行 revision。

待决（实现前需确认）：

- Q-1 是否在首个版本就提供“复制已有配置”以减少重复填 Key（建议提供，成本低）。
- Q-2 离线评测脚本是否接受 `DATABASE_URL` 依赖，还是必须同时提供完全离线的 CLI 配置（建议两者都保留）。
- Q-3 旧 `/chat/profiles*` 端点是否需要保留一个版本的只读兼容（当前规范为不保留）。

## 附录 A：交付切分（说明性，非规范）

- 切片 1：文档/ADR 冻结 + 两表/仓储/Provider/能力状态机 + 遗留导入。
- 切片 2：新 API + 前端模型/检索 store 拆分 + 设置页与快捷面板。
- 切片 3：参数接入、视觉固定身份、脚本/评测迁移、`.env` 清理与全量验收。

每个切片都必须满足对应验收标准；未通过真实 Provider/视觉验收的项必须标记为未运行，不能写成通过。
