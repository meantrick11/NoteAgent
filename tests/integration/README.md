# integration

组件边界：FastAPI 路由、RetrievalService + 临时 Chroma。不要连真实 DeepSeek。检索用假 embedding。

## 包含模块

| 文件 | 覆盖 |
|------|------|
| `test_app.py` | `GET /` 首页；`POST /chat` 为 SSE 且 `data:` 行可解析；会话历史/重命名/删除；`/chat/review`、`/chat/user_exit` |
| `test_retrieval_service.py` | 假向量下 index + search，metadata 带 `file_name` |

`test_app.py` 用 `FakeAgent` 注入 `AppContainer`，不跑 LangGraph。

## 基础使用

```bash
uv run pytest tests/integration -q
uv run pytest tests/integration/test_app.py::test_home_serves_template -q
```
