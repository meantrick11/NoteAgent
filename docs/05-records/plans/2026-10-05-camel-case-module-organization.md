# 上层模块驼峰命名与职责归属调整

## 已确认要求
用户要求上层模块使用驼峰命名，并且从模块名能够了解大致作用；本轮只调整上层包及职责归属。采用 lowerCamelCase。现有类、函数、底层文件名后续另行统一。

## 目标组织
- httpApi：chatApi、conversationApi、noteApi、modelSettingsApi、conversationRecoveryApi、webFrontend。
- businessModules：chatAgent、conversationState、noteStorage、noteRetrieval、modelSettings、conversationRecovery。
- applicationFlows：draftApproval、modelRuntime、conversationRecovery。
- technicalSupport：databaseAccess、executionLogging、noteAccessControl。
- appBootstrap：配置、对象装配、启动与关闭。
- chatAgent 下 conversationContext、systemPrompts；conversationState 下 legacyConversationCompatibility；noteRetrieval 下 indexRepair。
- noteStorage/changeJournal 持有笔记修改台账；technicalSupport/noteAccessControl 持有共享访问与维护状态；businessModules/conversationRecovery 持有恢复任务数据。

## 约束
类和方法名、数据库表名及列名、锁标识、HTTP 路径、前端持久化键、事务步骤沿用现有实现。拆开 ORM 归属后仍使用同一个 session/事务，不能分成多次提交。用户已有文档改动保持；不提交或发布。五入口之外的 tests、tools、evals 等仓库工具和数据目录保持用途命名。

## 执行清单
- [x] 新增结构回归约束，确认在旧结构上失败。
- [x] 迁移上层包与应用流程，拆分 workspace 中的数据归属，更新 Python 导入。
- [x] 同步提示词、前端构建、Docker、wheel 和文档链接。
- [x] 重写源码导航和职责 README，列出旧名到新名映射及完整路径区别。
- [x] 运行后端回归、前端构建及资源/链接检查，复核事务与数据标识未变化。

## 验证
pytest 完整套件与结构约束；npm frontend build；uv wheel 离线构建；README 链接、旧路径残留及 ORM 表名检查。

## 执行结果（2026-10-05）

- 已按目标迁移上层包与子模块，所有生产、测试、迁移及工具 Python 导入使用新路径。
- 原 workspace 已拆为共享访问控制、笔记修改台账、会话恢复数据三个归属；没有保留旧 workspace 兼容包。
- 各恢复记录、修改记录和共享状态仍在原 session 事务中读写；10 个 ORM 定义与全部既有函数实现经 AST 复核一致，只有路径、导入分组和归属变化。
- 现有 WorkspaceGate/WorkspaceState、数据库表列名、锁值、HTTP URL 沿用，底层符号未整体改名。
- 源码导航说明五入口、完整目录、易混淆职责和旧名映射，各包 README 与实际职责一致。
- 独立复核指出的 README 旧路径和接口名均已修正。

| 验证 | 结果 |
|---|---|
| 新增结构约束在旧结构上运行 | 2 项按预期失败 |
| 完整 pytest | 654 passed，1 skipped；Windows 不支持符号链接 |
| 定向结构与系统提示词检查 | 15 passed |
| 前端类型检查与 Vite 构建 | 通过，输出 httpApi/webFrontend/dist |
| wheel 离线构建与资源检查 | 通过，145 项文件；提示词、SPA、兼容页面与新 ORM 归属完整 |
| 源码及工具等 README 本地链接 | 42 份检查通过 |
| 三个评测 CLI --help | 通过 |
| alembic heads | e7b1c2f4a903，迁移链沿用 |
| 旧包导入检查 | 无生产、测试或工具残留 |
| 独立只读复核 | 导入、ORM、事务和资源路径通过 |

完整回归使用先前验证集群的本机临时 PostgreSQL 与测试隔离 schema；验证结束停止集群。用户已有 references、roadmap 和删除记录保持。diff --check 仅报告用户既有 references/思考.md 的空格。未执行提交或发布。
