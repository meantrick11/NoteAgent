# 恢复 HTTP

会话恢复预览、启动、状态和重试。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/ConversationRecoveryApi/ConversationRecoveryRoutes.py](ConversationRecoveryRoutes.py) | 路由与接口注册 |
| [HttpApi/ConversationRecoveryApi/ConversationRecoverySchemas.py](ConversationRecoverySchemas.py) | 请求响应结构 |

## 主要接口

调用 RecoveryCoordinator，确认范围由服务器预览决定。

## 依赖与约束

恢复算法在 ApplicationFlows/ConversationRecovery；路由不推断文件或 commit。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestRecoveryApi.py -q
```
