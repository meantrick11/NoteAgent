# Python 包与文件大驼峰命名

## 用户要求与范围
用户明确要求每个单词首字母大写，并扩展到子模块和单个 Python 文件。采用 PascalCase，名称同时表达职责。沿用已确认职责归属，本轮不再拆分业务行为。

- src/NoteAgent：全部自有包和 Python 文件采用 PascalCase。
- Scripts：入口脚本 PascalCase；Main.py 为主入口。
- Tools/NoteAgentEvals：评测包、子包、文件 PascalCase。
- Tests：Unit、Integration、Support、E2e，测试文件 Test*.py；函数名暂时沿用 pytest 的 test_ 约定。
- alembic/versions：现有迁移文件改为 PascalCase；revision/down_revision 标识保持。
- 框架特殊文件 __init__.py、__main__.py、conftest.py、env.py 保留。非 Python 的资源文件及 dist/templates/static 等目录沿用资源路径约定。

## 步骤
- [x] 新增源包/文件 PascalCase 约束，并确认在旧结构失败。
- [x] 建立每个包和文件的映射，在 Windows 安全执行两步改名；更新全部静态与动态导入。
- [x] 同步资源、构建、命令、测试发现模式和当前文档；保留用户与历史记录。
- [x] 完整测试、构建与大小写敏感检查，复核 ORM、函数实现和迁移链。
- [x] 更新阅读导航、命名例外和最终验证结果。

## 约束与验证
数据库表列、HTTP URL、持久化键、锁标识和事务协议不改；包名、文件名、模块 __module__ 值及运行命令随迁移更新。禁止对外兼容包掩盖旧路径。保持用户已存在的文档改动；不提交或发布。验证包括 pytest、Vite、wheel、评测 CLI、alembic heads、真实大小写路径和 README 链接。

## 执行结果（2026-10-05）

- src/NoteAgent 的五个入口和全部子包、Python 文件已采用 PascalCase；文件名补足业务用途。
- Main.py、Scripts、Tools/NoteAgentEvals、Tests 及现有 Alembic 迁移文件同步改名；pytest 使用 Test*.py 自动发现。
- Python、pytest、Alembic 特殊文件保留固定名称；类、函数和持久化标识未整体更名。
- 避免模块文件名与包导出类相同：装配使用 ContainerAssembly.py；模型配置持久化使用 ModelSettingsStorage.py；会话服务使用 ConversationStateService.py。
- 修正工具包、测试同目录导入、动态 monkeypatch 和恢复子进程脚本的旧路径。
- 顺带修复 BuildRagQueries.py 的既有失效导入：heading_path_at 直接从 MarkdownSections 导入。
- 13 项仅大小写改名通过 git mv 写入索引，文件内容 hash 保持，保证 Linux 检出包含 Main.py 等真实名称。其他内容修改保持在工作区；未提交或发布。
- CLAUDE.md 记录后续包/文件命名约定。旧结构历史记录保持，现行文档使用新路径。

| 验证 | 结果 |
|---|---|
| 新命名约束在旧结构 | 2 项预期失败 |
| 最终完整后端回归 | 656 passed，1 skipped；Windows 不支持符号链接 |
| 跨进程恢复定向回归 | 2 passed |
| 前端类型检查与 Vite 构建 | 通过；src/NoteAgent/HttpApi/WebFrontend/dist |
| wheel 离线构建与真实大小写资源检查 | 通过；145 项文件，当前提示词、SPA 和兼容页面齐全 |
| README 本地链接 | 58 份无失效链接 |
| 当前文档源码链接的精确大小写 | 通过 |
| 评测 CLI 与 BuildRagQueries --help | 通过 |
| alembic heads | e7b1c2f4a903，迁移链标识保留 |
| 独立静态复核 | 第三方导入、既有函数、10 个 ORM、checkpoint 节点和持久化键保持 |
| Git diff --check | 本轮无新增空白错误；只报告用户原有 references/思考.md 尾部空格 |

临时验证 PostgreSQL 复用已有本机集群、测试使用隔离 schema；验证结束停止集群，日常数据库配置未修改。

## 后续入口与交付调整

用户随后明确要求入口恢复为 main.py，并将本轮修改合并到 main 后推送 origin。已同步 Docker、启动命令、README、代码约定和入口大小写测试；main.py 是用户指定的命名例外。发布前重新检查入口结构测试和 Git 变更范围，排除用户原有 references、roadmap 和交接文档删除记录。
