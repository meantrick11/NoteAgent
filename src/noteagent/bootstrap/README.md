# bootstrap

读环境变量、把笔记仓库 / 检索 / Agent 装进容器、交出 FastAPI `app`。不写笔记、不调 LLM、不碰 Chroma。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `settings.py` | `Settings`、`project_root()` | 从 `.env` 读密钥、路径、模型名；相对路径接到仓库根 |
| `app.py` | `AppContainer`、`build_container`、`create_app` | 构造运行时依赖（含 `engine`、`history`）并挂到 `app.state.container`；shutdown 时 dispose engine |
| `__init__.py` | 再导出上述符号 | `from noteagent.bootstrap import Settings` |

## 基础使用

```python
from noteagent.bootstrap import Settings, build_container, create_app

settings = Settings()  # 读项目根 .env
container = build_container(settings)
app = create_app(container)
# HTTP 里取 Agent：request.app.state.container.chat_agent
```

测试不调真实模型时，可自己拼 `AppContainer` 再 `create_app(container)`，见 `tests/integration/test_app.py`。

```bash
uv run pytest tests/unit/test_settings.py tests/integration/test_app.py -q
```
