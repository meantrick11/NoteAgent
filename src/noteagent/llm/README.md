# llm

按 `Settings` 创建聊天模型。不放业务 prompt、不定义 Agent 工具。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `factory.py` | `create_chat_model` | `init_chat_model`，provider 为 deepseek |
| `__init__.py` | 再导出 | `from noteagent.llm import create_chat_model` |

## 基础使用

```python
from noteagent.bootstrap.settings import Settings
from noteagent.llm.factory import create_chat_model

settings = Settings()
model = create_chat_model(settings)
# 需要 .env 里 DEEPSEEK_API_KEY；可选 DEEPSEEK_API_BASE、CHAT_MODEL
```

密钥走 `SecretStr`，不要 `print(settings.deepseek_api_key.get_secret_value())` 到日志。

无真实 API 单测。连通性可用：

```bash
uv run python scripts/sdk_smoke.py
```
