# 共享技术能力

数据库连接、执行日志和笔记资源的并发访问控制。

## 子模块职责

| 模块 | 职责 |
|---|---|
| [DatabaseAccess/](DatabaseAccess/README.md) | 连接、session、Base、ORM 注册 |
| [ExecutionLogging/](ExecutionLogging/README.md) | Agent 和索引追踪、日志配置 |
| [NoteAccessControl/](NoteAccessControl/README.md) | 共享笔记资源访问锁与持久化维护状态 |

## 接口与依赖

供业务和流程使用；存储技术状态，不执行完整业务流程。

## 验证

从仓库根运行：`uv run pytest Tests/Unit/TestSourceOrganization.py -q`。
