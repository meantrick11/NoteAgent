# db

只放 `Base`、`Conversation` / `Message` 两张表、engine 与会话工厂。**不写 HTTP、不调 LLM。** 架构说明见 [`docs/architecture/database.md`](../../../docs/architecture/database.md)。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `models.py` | `Base`、`Conversation`、`Message` | 表结构（列名、索引、FK CASCADE）；含上下文列 `running_summary`、`summary_watermark_turn_id` 与 `Message` 的 `turn_id` / tool stub 字段 |
| `engine.py` | `create_engine_from_url`、`create_session_factory` | 同步 engine；SQLite 开 FK + `check_same_thread=False` |
| `__init__.py` | 再导出 | `from noteagent.db import Base, Conversation, Message, create_engine_from_url, create_session_factory` |

## 依赖方向

`chat` 可以 import `db`；`db` **不得** import `chat`。本包不 import `noteagent.retrieval`、`noteagent.llm`。

生产库用 PostgreSQL + Alembic（现行 head `3d1c2b8a9e4f`）。单测用内存 SQLite `Base.metadata.create_all`。业务写入口是 `ConversationStore`，不在本包。

## 基础使用

```python
from noteagent.db import Base, create_engine_from_url, create_session_factory

engine = create_engine_from_url("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = create_session_factory(engine)
```
