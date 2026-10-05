# NoteAgent 源码导航

自有 Python 包和文件统一使用 **PascalCase（大驼峰）**，每个单词首字母大写，并用业务对象与用途命名。示例：ChatAgent、NoteStorage、NoteAccessControl、ConversationStateService.py。

## 目录与职责

```text
NoteAgent/
├─ HttpApi/                         HTTP 请求、响应、错误映射
│  ├─ ChatApi/                      对话/SSE、草稿编辑与审核
│  ├─ ConversationApi/              会话列表、消息、重命名与删除
│  ├─ NoteApi/                      笔记和文件夹读写
│  ├─ ModelSettingsApi/             模型配置、测试、启用与重建接口
│  ├─ ConversationRecoveryApi/      恢复预览、确认和查询接口
│  └─ WebFrontend/                  SPA 分发与旧页面兼容
├─ BusinessModules/                 业务能力与持久化实现
│  ├─ ChatAgent/                    Agent 执行图、工具、事件与引用
│  │  ├─ ConversationContext/       token 预算、上下文压缩与装配
│  │  └─ SystemPrompts/             当前系统提示词
│  ├─ ConversationState/            会话状态、执行轮次、草稿与 checkpoint
│  │  └─ LegacyConversationCompatibility/  旧会话存储、导入和兼容审批
│  ├─ NoteStorage/                  Markdown 读写、正式修改和 Git 版本
│  │  └─ ChangeJournal/             笔记修改来源、版本、执行状态台账
│  ├─ NoteRetrieval/                切块、向量、索引和检索
│  │  └─ IndexRepair/               索引维修与重试记录
│  ├─ ModelSettings/                配置、凭据、候选、客户端与探测
│  └─ ConversationRecovery/         恢复预览与任务记录
├─ ApplicationFlows/                多个业务模块共同完成的流程
│  ├─ DraftApproval/                草稿审批和正式笔记修改协调
│  ├─ ModelRuntime/                 当前运行快照、模型切换、索引重建协调
│  └─ ConversationRecovery/         恢复规划、执行、发布与重试
├─ TechnicalSupport/                共用技术能力
│  ├─ DatabaseAccess/               数据库连接、Base 与 ORM 注册
│  ├─ ExecutionLogging/             Agent、索引运行日志
│  └─ NoteAccessControl/            笔记资源的共享访问、互斥与维护状态
└─ AppBootstrap/                    配置、对象装配、启动与关闭
```

## 五个阅读入口

| 入口 | 先读什么 | 解决什么问题 |
|---|---|---|
| [HttpApi](HttpApi/README.md) | ApiRoutes.py | 哪些请求进入系统、交给谁 |
| [BusinessModules](BusinessModules/README.md) | 业务包 README | 功能与数据归谁管理 |
| [ApplicationFlows](ApplicationFlows/README.md) | 各流程 README | 审批、切换、恢复如何跨模块完成 |
| [TechnicalSupport](TechnicalSupport/README.md) | 各技术包 README | 连接、锁与日志如何提供 |
| [AppBootstrap](AppBootstrap/README.md) | ContainerAssembly.py | 所有运行对象如何创建与连接 |

## 按任务查代码

| 任务 | HTTP 入口 | 核心实现 |
|---|---|---|
| 对话、SSE | HttpApi/ChatApi | BusinessModules/ChatAgent + ConversationState/TurnExecution.py |
| 会话与消息 | HttpApi/ConversationApi | BusinessModules/ConversationState |
| 编辑和批准草稿 | HttpApi/ChatApi | ApplicationFlows/DraftApproval/DraftApprovalWorkflow.py |
| 读写正式笔记 | HttpApi/NoteApi | BusinessModules/NoteStorage/MarkdownRepository.py、NoteChanges.py |
| 笔记修改台账 | 由修改流程调用 | BusinessModules/NoteStorage/ChangeJournal |
| 检索与索引维修 | Agent 工具、笔记接口 | BusinessModules/NoteRetrieval |
| 模型配置和探测 | HttpApi/ModelSettingsApi | BusinessModules/ModelSettings |
| 模型运行切换与重建 | HttpApi/ModelSettingsApi | ApplicationFlows/ModelRuntime/ModelRuntime.py |
| 历史消息编辑与恢复 | HttpApi/ConversationRecoveryApi | ApplicationFlows/ConversationRecovery |
| 聊天、读写、恢复、重建的互斥 | 共享依赖和流程 | TechnicalSupport/NoteAccessControl |

## 容易混淆的包

- BusinessModules/ConversationRecovery 保存预览与任务数据；ApplicationFlows/ConversationRecovery 执行恢复流程；HttpApi/ConversationRecoveryApi 接收请求。
- NoteStorage/ChangeJournal 记录正式笔记修改；NoteAccessControl 协调所有进程对共享笔记资源的访问。读和聊天可共享，修改、恢复和索引重建需要独占；中断维护状态持久化后不会因进程退出而自动开放写入。
- ModelSettings 管配置、凭据与探测；ModelRuntime 管当前生效对象与切换流程。
- HTTP 只出现在 HttpApi；BusinessModules 和 ApplicationFlows 不导入 FastAPI。
- 五个入口按职责组织，一次请求不必依次经过五层。

## 数据与事务

Markdown 正文位于 notes/；PostgreSQL 保存会话、checkpoint、台账和恢复任务；Chroma 是可重建的检索索引；影子 Git 保存笔记版本。
数据库表名、列名和原子事务沿用既有定义，ORM 归属拆开后仍共享同一 session。WorkspaceState、WorkspaceGate 等现有类名及 workspace_state 数据表是底层兼容标识，本轮不改。

## 旧名到新名

| 旧包 | 新包 |
|---|---|
| api | HttpApi |
| modules/assistant | BusinessModules/ChatAgent |
| modules/conversations | BusinessModules/ConversationState |
| modules/notes | BusinessModules/NoteStorage |
| modules/retrieval | BusinessModules/NoteRetrieval |
| modules/models | BusinessModules/ModelSettings |
| modules/workspace/gate、WorkspaceState | TechnicalSupport/NoteAccessControl |
| modules/workspace/journal、MutationRecord | BusinessModules/NoteStorage/ChangeJournal |
| modules/workspace/RecoveryPreview、RecoveryJob | BusinessModules/ConversationRecovery |
| application/approvals.py | ApplicationFlows/DraftApproval/DraftApprovalWorkflow.py |
| application/model_runtime.py | ApplicationFlows/ModelRuntime/ModelRuntime.py |
| application/recovery | ApplicationFlows/ConversationRecovery |
| infrastructure/database | TechnicalSupport/DatabaseAccess |
| infrastructure/observability | TechnicalSupport/ExecutionLogging |
| bootstrap | AppBootstrap |

历史记录中的旧路径表示当时结构，当前源码以本导航为准。评测实现见 [tools](../../Tools/NoteAgentEvals/README.md)，提示词历史见 [evals](../../evals/prompt/iterations/README.md)。

## 验证与本轮范围

从仓库根运行 `uv run pytest -q`；结构、导入方向、ORM 归属和资源路径约束在 Tests/Unit/TestSourceOrganization.py。
本轮完成自有 Python 包与文件的命名整理；ModelRuntime.py、ConversationStateService.py 等内部职责拆分另行开展。类、函数和字段名沿用现有接口。

## Python 命名规则与例外

- 包和文件用 PascalCase，例如 NoteAgent/BusinessModules/NoteStorage/NoteChanges.py。
- 主入口为 main.py；维护脚本在 Scripts；评测代码在 Tools/NoteAgentEvals。
- 测试位于 Tests/Unit、Tests/Integration 等，文件为 Test*.py；pytest 已配置新的发现模式。
- 入口 main.py 按用户要求保留小写；Python 的 __init__.py、__main__.py，pytest 的 conftest.py 和 Alembic 的 env.py 保留框架固定名称。
- Alembic 迁移文件采用 PascalCase，revision/down_revision 值沿用原迁移链。
- 第三方包名、安装分发名 noteagent、HTTP 地址、数据库标识和资源文件名沿用各自协议。

## 入口阅读顺序

main.py → [ContainerAssembly.py](AppBootstrap/ContainerAssembly.py) → [HttpApp.py](AppBootstrap/HttpApp.py) → [ApiRoutes.py](HttpApi/ApiRoutes.py)。
正式笔记修改从 [NoteRoutes.py](HttpApi/NoteApi/NoteRoutes.py) 进入 [NoteChanges.py](BusinessModules/NoteStorage/NoteChanges.py)；聊天执行从 [ChatRoutes.py](HttpApi/ChatApi/ChatRoutes.py) 进入 [ChatAgent.py](BusinessModules/ChatAgent/ChatAgent.py) 和 [ChatGraph.py](BusinessModules/ChatAgent/ChatGraph.py)。
