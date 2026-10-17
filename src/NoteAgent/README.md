# NoteAgent 后端源码导航

后端是一个 FastAPI 应用。业务代码按模块归属；每个模块自行管理 HTTP 入口、传输对象、业务流程和持久化实现。前端工程位于仓库根目录的 `frontend/`。

## 顶层目录

| 目录 | 职责 |
|---|---|
| [AppBootstrap/](AppBootstrap/README.md) | 配置、依赖装配、应用生命周期及总路由注册 |
| [Modules/](Modules/README.md) | 会话、聊天、笔记、检索、模型、来源和恢复 |
| [Common/](Common/README.md) | 数据库连接与 ORM Base、日志、共享访问门禁及 HTTP 公共依赖 |
| [WebFrontend/](WebFrontend/README.md) | 已构建 Vue 页面和旧首页的托管入口 |

入口调用顺序：`main.py` → `AppBootstrap/ContainerAssembly.py` → `AppBootstrap/HttpApp.py` → `AppBootstrap/ApiRoutes.py` → 各模块 `Router/`。

## 模块内部约定

- `Router/`：FastAPI 路由；只负责 HTTP 参数、状态码与响应转换。
- `Domain/Dto/`：请求与响应对象；`Domain/Vo/`：业务值、结果及错误；`Domain/Po/`：SQLAlchemy 表映射。没有对应对象的模块不建空目录。
- `Service/`：用例与跨模块流程。正式笔记写入由 Notes 负责；Chat 的草稿审批和 Recovery 的恢复流程调用它。
- `Mapper/`：业务表读写。文件、Git、Chroma、LLM 等具体能力使用模块内的 `Storage/`、`Engine/`、`Provider/`、`Parser/` 等专属目录。

常规跨模块调用经过对方的明确入口。现有恢复与会话事务仍会共同访问多个模块的 ORM 表；这类调用须保留原事务边界，不能仅为消除 import 而拆成多个提交。跨模块共享的数据库连接和访问门禁位于 `Common/`，对象创建集中在 `AppBootstrap/`。

## 验证

后端单元测试：`.venv/Scripts/python.exe -m pytest Tests/Unit -q`；源码组织约束位于 [TestSourceOrganization.py](../../Tests/Unit/TestSourceOrganization.py)。数据库迁移统一位于仓库根目录的 `alembic/versions/`，不拆为模块独立迁移链。
