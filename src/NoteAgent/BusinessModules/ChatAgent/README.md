# Agent 执行

图、节点、工具、上下文和执行事件。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/ChatAgent/ChatAgent.py](ChatAgent.py) | Agent 门面 |
| [BusinessModules/ChatAgent/CitationRegistry.py](CitationRegistry.py) | 引用映射 |
| [BusinessModules/ChatAgent/ChatEvents.py](ChatEvents.py) | 执行事件 |
| [BusinessModules/ChatAgent/ChatExecution.py](ChatExecution.py) | 执行和中断 |
| [BusinessModules/ChatAgent/ChatGraph.py](ChatGraph.py) | 图结构 |
| [BusinessModules/ChatAgent/ChatNodes.py](ChatNodes.py) | 图节点 |
| [BusinessModules/ChatAgent/ChatTools.py](ChatTools.py) | Agent 工具 |
| [ConversationContext/](ConversationContext/README.md) | token 估算、预算、消息压缩和上下文装配 |
| [SystemPrompts/](SystemPrompts/README.md) | 当前生产使用的系统提示词 |

## 主要接口

ChatAgent.prepare/run/stream 是执行接口；review/update_draft_content 委托 DraftApproval。

## 依赖与约束

会话权威状态由 ConversationState 管理，具体审批流程由 AppBootstrap 注入。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestChatGraph.py Tests/Unit/TestGraphExecution.py -q
```
