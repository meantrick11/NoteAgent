# observability

进程日志、LangChain 回调追踪、检索步骤追踪。不记 API key、不把整份网页/笔记正文打进 INFO。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `logging.py` | `setup_logging`、`ColoredFormatter` | 配输出：彩色 stdout + `log_dir/noteagent.log` 轮转。不写业务事件文案 |
| `agent_trace.py` | `AgentTraceHandler` | LLM/工具 start、end、error、耗时、截断回复（LangChain callback） |
| `index_trace.py` | `IndexTrace` | 索引/检索步骤 INFO（start/delete/chunked/embedded/upserted/done/skip/search） |
| `__init__.py` | 再导出 | `setup_logging`、`AgentTraceHandler`、`IndexTrace` |

`openai` 等第三方 logger 被压到 WARNING，避免把完整 prompt JSON 灌进 DEBUG。

切块、embed、写 Chroma 在 [`retrieval`](../retrieval/README.md)，本包只打步骤事件。

## 基础使用

```python
from pathlib import Path
import logging
from noteagent.observability.logging import setup_logging
from noteagent.observability.agent_trace import AgentTraceHandler
from noteagent.observability.index_trace import IndexTrace

setup_logging(Path("var/logs"), level=logging.DEBUG)
# Agent 运行配置里 callbacks=[AgentTraceHandler()]
# RetrievalService(trace=IndexTrace()) 默认已自建
```

`main.py` 启动时会调用 `setup_logging`。看文件：

```text
var/logs/noteagent.log
```
