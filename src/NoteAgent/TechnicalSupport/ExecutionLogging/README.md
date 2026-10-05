# 日志和追踪

应用日志、Agent/LLM/工具和索引事件。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [TechnicalSupport/ExecutionLogging/AgentTrace.py](AgentTrace.py) | 执行追踪 |
| [TechnicalSupport/ExecutionLogging/IndexTrace.py](IndexTrace.py) | 索引追踪 |
| [TechnicalSupport/ExecutionLogging/LoggingSetup.py](LoggingSetup.py) | 日志配置 |

## 主要接口

setup_logging 配置日志，AgentTraceHandler 与 IndexTrace 记录运行。

## 依赖与约束

日志目录保持原配置，由装配层或使用方注入。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestChatTools.py -q
```
