# 上下文处理

集中 token 计量、预算、消息组织和摘要压缩。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/ChatAgent/ConversationContext/ContextBudget.py](ContextBudget.py) | 预算 |
| [BusinessModules/ChatAgent/ConversationContext/ContextCompaction.py](ContextCompaction.py) | 压缩 |
| [BusinessModules/ChatAgent/ConversationContext/ContextPack.py](ContextPack.py) | 上下文打包 |
| [BusinessModules/ChatAgent/ConversationContext/TokenCounter.py](TokenCounter.py) | token 计量 |

## 主要接口

ContextBudget.py、TokenCounter.py、ContextPack.py、ContextCompaction.py 对应预算、计量、组装和压缩。

## 依赖与约束

保留摘要水位、工具 stub 和预算规则。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestContextBudget.py Tests/Unit/TestContextTokens.py Tests/Unit/TestContextPack.py Tests/Unit/TestContextCompact.py -q
```
