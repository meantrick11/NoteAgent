# 会话 HTTP

提供会话列表、详情、消息、重命名与删除。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/ConversationApi/ConversationRoutes.py](ConversationRoutes.py) | 路由与接口注册 |
| [HttpApi/ConversationApi/ConversationSchemas.py](ConversationSchemas.py) | 请求响应结构 |

## 主要接口

ConversationRoutes.py 投影消息、草稿、运行和恢复状态。

## 依赖与约束

侧栏元数据用 legacy store，checkpoint 正文用 ConversationService。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestCheckpointChatApi.py -q
```
