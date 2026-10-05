# NoteAgent 源码组织实施计划

**目标：** 将源码组织为 API、业务模块、跨模块流程、基础设施和装配五个入口，同步 README，保持 HTTP、checkpoint、数据库表和运行数据格式不变。

**设计依据：** 本聊天已确认的 `api / modules / application / infrastructure / bootstrap` 方案。

**约束：** Python 3.13；FastAPI、LangGraph、SQLAlchemy；沿用现有依赖与数据迁移；保留旧前端和旧会话导入能力；保留工作区已有文档修改；不提交、不部署。

## 文件和接口归属

- `api/{chat,conversations,notes,models,recovery,web}`：路由和 HTTP 请求响应结构；`dependencies.py` 管理运行快照租约和同源检查，`errors.py` 管理异常响应，`router.py` 汇总接口。
- `modules/assistant`：Agent 图、工具、执行、上下文和当前提示词。
- `modules/conversations`：会话记录、状态、草稿、运行租约、checkpoint 和 ORM；`legacy` 保留旧存储和导入。
- `modules/notes`：正式写入、Markdown 存取和影子 Git。
- `modules/retrieval`：检索与索引维修，维修 ORM 归属 `indexing`。
- `modules/models`：模型配置、候选、连接测试和客户端；内部契约与 HTTP schema 分离。
- `modules/workspace`：工作区门禁、状态与写操作记录。
- `application`：审批、模型运行管理和恢复协调。
- `infrastructure`：数据库 Base、连接与 ORM 注册；日志追踪。
- `bootstrap`：容器、装配、生命周期和应用创建。
- `tools/noteagent_evals`：评测实现；`scripts` 保持现有命令入口。

## 执行步骤

- [x] 1. 运行现有测试建立基线；新增架构检查，验证目标路径、业务包不依赖 HTTP、ORM 注册与静态产物路径，先确认现有结构失败。
- [x] 2. 按明确文件映射移动源码、统一更新 Python 导入和测试 monkeypatch 路径；拆 API 会话路由、数据库 Base 和各职责 ORM；执行收集与结构检查。
- [x] 3. 将审批协调移出 Agent，将模型配置/探测与运行管理分开，将会话运行实现与生命周期装配收拢；用现有审批、会话、模型、恢复行为测试验证。
- [x] 4. 更新评测加载路径、Vite/Docker/wheel/ignore 产物路径；保留磁盘数据目录和配置名。
- [x] 5. 为各层和业务模块编写 README（职责、文件索引、接口、依赖、兼容说明、验证入口），更新根 README 与现行架构文档的源码链接。
- [x] 6. 运行完整 Python 测试、前端验证及 wheel 资源检查；审查变更和文档链接，独立 reviewer 检查后修复问题。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_source_organization.py -q
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run build
npm --prefix frontend run test:unit
```

所有数据库集成测试沿用现有隔离 schema fixture。源码模块路径可以变更，HTTP 路径、数据表名、凭据存储格式和幂等操作标识保持一致。

## 执行结果（2026-10-05）

- 已完成五个源码入口、业务模块聚合、HTTP 路由集中、跨模块流程提取、ORM 按职责归属和启动装配拆分。
- ConversationRuns 和 MutationJournal 保留原事务步骤；Agent 通过 DraftApproval 接口调用审批流程。
- recovery job ORM 留在 workspace：会话发布与恢复任务需要共享原有原子事务。
- 旧会话存储保留在 conversations/legacy，旧前端保留在 api/web；历史提示词移到 evals/prompt/iterations，评测实现移到 tools/noteagent_evals。
- 模型客户端对 Settings 的类型依赖沿用现有实现；未来可通过配置接口收窄，当前不改变配置行为。
- README 提供职责、文件索引、接口、依赖与验证命令；当前源码与工具等 38 份 README 本地链接检查通过。

### 验证记录

| 验证 | 结果 |
|---|---|
| 完整后端 pytest | 652 passed，1 skipped；Windows 不支持符号链接而跳过一项 |
| 最后清理后的单元测试 | 448 passed |
| 前端单元测试 | 145 passed |
| 前端 Vite 构建 | 通过，输出 api/web/dist |
| wheel 离线构建及资源检查 | 通过，包含当前提示词、SPA 和兼容页面；不含评测实现及历史提示词 |
| eval_notes / eval_rag / eval_rag_agent --help | 通过 |
| alembic heads | e7b1c2f4a903，沿用原迁移链 |
| 独立源码与 README 复核 | 已修复两项功能回归及两处文档描述，无剩余问题 |

完整后端验证使用本机 loopback 的临时 PostgreSQL 集群及 fixture 隔离 schema，未修改日常数据库配置。保留原有用户文档改动。git diff --check 仅报告用户既有 references/思考.md 的尾部空格；本次变更无新增空白错误。未执行提交或发布。

验证用临时 PostgreSQL 已停止；删除临时目录的命令被自动安全策略拦截，未继续尝试。保留目录：C:/Users/lenovo/AppData/Local/Temp/noteagent-reorg-pg-he3pnhja。
