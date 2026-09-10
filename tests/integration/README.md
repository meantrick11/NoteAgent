# integration

组件边界：FastAPI 路由、RetrievalService + 临时 Chroma。不要连真实 DeepSeek。检索用假 embedding。

## 包含模块

| 文件 | 覆盖 |
|------|------|
| `test_app.py` | 首页、Documents 路由、SSE 多 token、会话 CRUD、`pending_draft`、messages 隐藏 tool 行但带 `tool_steps` |
| `test_notes_api.py` | Documents HTTP：保存重索引、move 清旧向量、列表 indexed |
| `test_retrieval_service.py` | 假向量下 index + search；reindex 去掉旧 chunk；审批 create 后可搜；索引步骤 INFO |

`test_app.py` 用 `FakeAgent` 注入 `AppContainer`，不跑真实模型。

## 基础使用

```bash
uv run pytest tests/integration -q
uv run pytest tests/integration/test_app.py::test_home_serves_template -q
```
