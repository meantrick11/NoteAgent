# 上下文处理

集中 token 计量、预算、消息组织和摘要压缩。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [Modules/Chat/Agent/Context/ContextBudget.py](ContextBudget.py) | 预算 |
| [Modules/Chat/Agent/Context/ContextCompaction.py](ContextCompaction.py) | 压缩 |
| [Modules/Chat/Agent/Context/ContextPack.py](ContextPack.py) | 上下文打包 |
| [Modules/Chat/Agent/Context/TokenCounter.py](TokenCounter.py) | token 计量 |

## 主要接口

ContextBudget.py、TokenCounter.py、ContextPack.py、ContextCompaction.py 对应预算、计量、组装和压缩。

## 依赖与约束

保留摘要水位、工具 stub 和预算规则。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/Modules/Chat/TestContextBudget.py Tests/Unit/Modules/Chat/TestContextTokens.py Tests/Unit/Modules/Chat/TestContextPack.py Tests/Unit/Modules/Chat/TestContextCompact.py -q
```
