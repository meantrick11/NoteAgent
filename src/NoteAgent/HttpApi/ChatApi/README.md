# 聊天 HTTP

提供 POST /chat、草稿编辑与审批；保留幂等键、revision、prepared turn 和续跑协议。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/ChatApi/ChatRoutes.py](ChatRoutes.py) | 路由与接口注册 |
| [HttpApi/ChatApi/ChatSchemas.py](ChatSchemas.py) | 请求响应结构 |

## 主要接口

路由调用 Agent prepare/run/review，ChatSchemas.py 定义聊天请求。

## 依赖与约束

会话资源接口在 ../conversations；审批由注入的流程实现。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestCheckpointChatApi.py Tests/Integration/TestCheckpointDraftApi.py -q
```
