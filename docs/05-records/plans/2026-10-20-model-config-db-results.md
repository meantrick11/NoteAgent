# 模型配置数据库化：执行结果

日期：2026-10-20。规范见 [2026-10-20-model-config-db-spec.md](2026-10-20-model-config-db-spec.md)，上层决策见 [ADR-003](../../../../NoteAgent-docs/docs/03-architecture/ADR/ADR-003-模型配置数据库化与通用Provider.md) 与 [CR-2026-006](../../../../NoteAgent-docs/docs/09-decisions/CR-2026-006-模型配置数据库化与通用Provider.md)。

## 已实现

- PostgreSQL 两张表：`model_configs`（每条模型配置一行、行级 revision、`is_active` 部分唯一索引）与 `model_capabilities`（每个能力一行，含启用/验证/来源/时间/探针版本/证据）。
- 领域聚合、能力状态机、Provider 注册表（`deepseek` / `openai` / `openai-compatible`）与统一客户端工厂；领域与 Service 不再包含供应商专属分支。
- SQL 仓储：行级 CAS、active 切换事务、能力原位更新、删除保护、幂等导入；旧 `var/model_settings/settings.json` 导入为两表并保留 `settings.pre-db.json`。
- 运行时改为从仓储加载 active 模型与能力；无 active 时降级启动，聊天返回 503 `model_not_configured`；active 不可用时 fail-fast。
- 新 HTTP 契约：`models` CRUD、`providers`、`test`、`activate`（可携带完整配置）、能力 verify/disable；旧 `/chat/profiles*` 下线。
- 视觉解析按上传时固定的 model id + 行 revision 读取能力行，不再重读配置文件；active 切换不改变已入队来源。
- 前端模型入口改为多配置列表、Provider 规格表单、行级 revision 与能力徽章；模型与检索 revision 分离。
- 评测/脚本（`EvalNotes.py`、`CalibrateLearningNotes.py`、RAG `AgentRun.py`、`SdkSmoke.py`）改为通过 `Tools/NoteAgentEvals/ModelResolver.py` 解析数据库 active 模型；Judge 支持 `--judge-model` 复用同一连接。

## 验证结果

| 检查 | 结果 |
|---|---|
| 后端单测 + 集成 | `737 passed, 1 skipped` |
| 模型定向测试 | `143 passed` |
| 前端类型检查 | 通过 |
| 前端单测 | `149 passed` |
| 前端 e2e（Edge） | `73 passed` |
| 前端构建 | 通过 |
| Alembic 隔离 schema | `upgrade head` → `downgrade a61d9e2c4f37` → `upgrade head` 通过；两张表、`ux_model_configs_active` 索引存在 |
| 隔离启动冒烟 | 临时 schema + 临时目录：`GET /` 200、`GET /model-settings` 200（models 空、active null）、`GET /providers` 200、`POST /chat` 503 `model_not_configured` |

## 未运行

- 真实 Provider 请求（生成/评测/Judge）未运行，避免消耗账户额度；真实模型的 text/vision 探测仍按项目惯例单独记录。
- 真实用户数据库迁移未在本轮执行；应用下次启动会执行 Alembic 迁移并导入现有 `settings.json`，导入前自动生成 `settings.pre-db.json`。
- Docker 镜像未重新构建；本轮使用本机 PostgreSQL、独立测试 schema 与前端构建验证。
- 多用户、密钥加密、跨进程快照失效仍是非目标。

## 迁移与回滚

1. 启动前备份 PostgreSQL 与 `var/model_settings/settings.json`。
2. 启动应用：Alembic 建表 → 导入旧 profile/能力/active → 生成 `settings.pre-db.json` → 原文件只保留 embedding 字段。
3. 回滚：停服 → `alembic downgrade a61d9e2c4f37` → 将 `settings.pre-db.json` 还原为 `settings.json` → 回退代码。
4. 数据库备份现在包含模型凭据；分享、演练与日志必须脱敏。

## 遗留与后续

- `ModelSettingsStore` 仍保留用于 Retrieval embedding 状态与一次性导入；后续检索模块迁移时再移除。
- `Scripts/IndexNotes.py` 仍读该 store 的 embedding 状态，符合当前边界。
- `.env` 中 `DEEPSEEK_API_KEY` 等旧变量只在迁移导入时使用；新安装不再需要。
- 串行执行中的“模型行 revision + embedding revision”已分域；前端不再使用全局 revision。
