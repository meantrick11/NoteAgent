# HTTP 接口

接收 HTTP 请求，验证输入，调用业务能力或跨模块流程，返回响应。

## 子模块职责

| 模块 | 职责 |
|---|---|
| [ChatApi/](ChatApi/README.md) | 聊天、SSE、草稿编辑和审核接口 |
| [ConversationApi/](ConversationApi/README.md) | 会话元数据和消息接口 |
| [NoteApi/](NoteApi/README.md) | 笔记、文件夹和版本接口 |
| [ModelSettingsApi/](ModelSettingsApi/README.md) | 模型配置、探测、切换和索引重建接口 |
| [ConversationRecoveryApi/](ConversationRecoveryApi/README.md) | 恢复预览、确认和任务查询接口 |
| [WebFrontend/](WebFrontend/README.md) | SPA 分发与旧页面兼容 |

辅助文件：ApiRoutes.py、RequestDependencies.py、HttpErrors.py。

## 接口与依赖

ApiRoutes.py 统一注册；RequestDependencies.py 提供租约和运行快照；HttpErrors.py 统一映射异常。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestApp.py -q`。
