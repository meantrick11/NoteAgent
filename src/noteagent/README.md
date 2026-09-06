# noteagent

应用包。按能力分包：装配、聊天、笔记文件、检索、模型、日志、页面。全局架构见 [`docs/architecture/architecture.md`](../../docs/architecture/architecture.md)。

## 包含模块

| 子包 | 做什么 |
|------|--------|
| [`bootstrap/`](bootstrap/README.md) | `Settings`、组装依赖、创建 FastAPI |
| [`chat/`](chat/README.md) | SSE 聊天、会话历史、Agent、上下文压缩、草稿审批 |
| [`db/`](db/README.md) | 会话/消息表、engine（只放 ORM，不写 HTTP/LLM） |
| [`notes/`](notes/README.md) | 读写 `notes/` 下的 Markdown |
| [`llm/`](llm/README.md) | 根据配置创建聊天模型 |
| [`retrieval/`](retrieval/README.md) | 切块、向量、Chroma 检索 |
| [`observability/`](observability/README.md) | 进程日志、LLM/工具追踪、索引步骤 |
| [`web/`](web/README.md) | HTML 模板（Chat / Documents，见 [frontend.md](../../docs/architecture/frontend.md)） |
| [`prompt_eval/`](prompt_eval/README.md) | 离线提示词评测（chat 不得 import） |

依赖方向：`chat` 可以调 `notes`、`retrieval`、`llm`、`observability`、`db`。`retrieval` 可调 `observability`（`IndexTrace`）。`notes`、`retrieval` 与 `db` 不得 import `chat`。`prompt_eval` 可以调 `chat`；`chat` 不得 import `prompt_eval`。

系统提示在 [`chat/prompts/`](chat/prompts/README.md)。记笔记评测准则在 [`docs/evaluations/`](../../docs/evaluations/README.md)，黄金集与跑分结果在仓库根 [`evals/`](../../evals/README.md)。

## 基础使用

进程入口（`main.py` 已封装）：

```python
from noteagent.bootstrap import Settings, build_container, create_app

settings = Settings()
app = create_app(build_container(settings))
```

```bash
uv run pytest -q
```
