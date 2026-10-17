# NoteAgent 目录约定

此文件是 `coding-architecture-git` 在 NoteAgent 仓库中的实例。代码现状是最终依据；以下树展示职责和归属，不要求创建尚无内容的目录。

```text
NoteAgent/
├─ src/NoteAgent/
│  ├─ AppBootstrap/            # 启动、配置、依赖装配、生命周期、路由注册
│  ├─ Common/                  # 数据库连接、日志、共享访问门禁、HTTP 公共依赖
│  ├─ Modules/
│  │  ├─ Chat/                 # Router、Domain、Service、Agent
│  │  ├─ Conversations/        # Router、Domain、Service、Checkpoint、Legacy
│  │  ├─ Notes/                # Router、Domain、Service、Mapper、Storage
│  │  ├─ Models/               # Router、Domain、Service、Mapper、Provider
│  │  ├─ Sources/              # Router、Domain、Service、Mapper、Parser、Storage
│  │  ├─ Recovery/             # Router、Domain、Service
│  │  └─ Retrieval/            # Domain、Service、Engine；当前无独立 HTTP 入口
│  └─ WebFrontend/             # Vue 构建产物和静态页面的托管入口
├─ frontend/                   # 独立 Vue 工程
│  ├─ src/
│  │  ├─ features/             # chat、notes、models、source-files 等功能
│  │  ├─ layouts/
│  │  ├─ pages/
│  │  ├─ shared/
│  │  └─ styles/
│  ├─ tests/
│  │  ├─ unit/
│  │  ├─ e2e/
│  │  └─ fixtures/
│  ├─ package.json
│  ├─ package-lock.json
│  └─ vite.config.ts
├─ Tests/                      # Python 测试
│  ├─ Unit/Modules/           # 按业务模块归类
│  ├─ Integration/
│  ├─ E2e/
│  ├─ Support/
│  └─ conftest.py
├─ alembic/                    # 全应用共用的数据库迁移链
│  ├─ versions/
│  └─ env.py
├─ Scripts/                    # 开发、迁移和运维时执行的脚本
├─ Tools/                      # 可复用内部工具
├─ evals/                      # 评测标准、样例、结果与报告
│  ├─ criteria/
│  ├─ prompt/
│  ├─ rag/
│  ├─ agent/
│  └─ reports/
├─ docs/                       # 当前文档、历史记录及资源
│  ├─ 00-overview/
│  ├─ 01-architecture/
│  ├─ 02-api/
│  ├─ 03-modules/
│  ├─ 04-ops/
│  ├─ 05-records/
│  ├─ 06-releases/
│  └─ 07-assets/
├─ docker/
│  └─ entrypoint.sh
├─ Dockerfile
├─ docker-compose.yml
├─ main.py                     # Python 应用入口
├─ pyproject.toml              # Python 包、依赖和测试配置
├─ uv.lock
├─ alembic.ini
├─ .python-version
├─ .env.example                # 可提交的配置示例
├─ .gitignore
├─ .dockerignore
├─ README.md                   # 项目入口
├─ CONTEXT.md                  # 业务术语
└─ CLAUDE.md                   # 仓库协作约定
```

典型模块内部按实际职责展开：

```text
Modules/Notes/
├─ Router/                      # HTTP 路由；不承载核心业务规则
├─ Domain/
│  ├─ Dto/                     # 请求与响应模型
│  └─ Po/                      # 持久化模型；有对应模型时才建
├─ Service/                     # 笔记用例与流程
├─ Mapper/                      # 数据库读写
└─ Storage/                     # Markdown 和版本文件的存储实现
```

`AppBootstrap/ApiRoutes.py` 仅汇总各模块 Router。`WebFrontend/WebRoutes.py` 处理前端页面和静态资源托管。`Retrieval` 当前由其他模块的用例调用，因此没有空的 `Router/`。

项目自有 Python 包和文件遵循 `CLAUDE.md` 的 PascalCase 约定；`main.py`、`__init__.py`、`conftest.py`、Alembic `env.py` 等约定名称保留。
