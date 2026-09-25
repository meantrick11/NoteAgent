# bootstrap

读环境变量、把笔记仓库 / 模型运行时 / 历史装进容器、交出 FastAPI `app`。不写笔记、不调 LLM、不碰 Chroma。缺 `DATABASE_URL` 时 `build_container` 失败。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `settings.py` | `Settings`、`project_root()` | `.env`：密钥、路径、模型、**上下文窗口/压缩/stub/`CHAT_MAX_TOOL_HOPS`**、`MODEL_SETTINGS_DIR`；`JUDGE_MODEL` 仅离线评测 |
| `runtime.py` | `BootstrapAssembler`、`budget_for_window`、`api_key_for_profile` | 唯一的 Agent / 工具 / 检索装配入口，注入给 `ModelRuntimeService` |
| `app.py` | `AppContainer`、`build_container`、`create_app` | 构造 engine / history / notes，装配 `ModelRuntimeService` 并 `initialize()`；挂载 `/static`、注册错误处理与路由；shutdown 停任务后 dispose engine |
| `__init__.py` | 再导出上述符号 | `from noteagent.bootstrap import Settings` |

## 基础使用

```python
from noteagent.bootstrap import Settings, build_container, create_app

settings = Settings()  # 读项目根 .env
container = build_container(settings)
app = create_app(container)
# HTTP 里取一次运行快照：request.app.state.container.model_runtime.chat()
```

`AppContainer.retrieval` / `.chat_agent` 只作只读兼容视图；生产请求必须通过 `model_runtime` 的租约取快照，否则切换期间会拿到不一致的对象。

测试不调真实模型时，可自己拼 `AppContainer` + 一个假 `RuntimeAssembler` 再 `create_app(container)`，见 `tests/integration/test_app.py`。

```bash
uv run pytest tests/unit/test_settings.py tests/integration/test_app.py -q
```
