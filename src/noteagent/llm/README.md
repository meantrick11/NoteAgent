# llm

按 `Settings` 或显式配置创建聊天模型。不放业务 prompt、不定义 Agent 工具。不依赖 HTTP，也不读模型配置存储。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `factory.py` | `create_chat_model`、`create_judge_model` | 从 `Settings` 建模型，provider 为 deepseek；Judge 只给离线评测用 |
| `factory.py` | `create_chat_model_from_config` | 按界面 profile 的 provider/model/base_url/api_key 建模型；`openai-compatible` 映射到 openai 集成 |
| `__init__.py` | 再导出 | `from noteagent.llm import create_chat_model` |

## 基础使用

```python
from noteagent.bootstrap.settings import Settings
from noteagent.llm.factory import create_chat_model

settings = Settings()
model = create_chat_model(settings)
# 需要 .env 里 DEEPSEEK_API_KEY；可选 DEEPSEEK_API_BASE、CHAT_MODEL
# 离线评测可选 JUDGE_MODEL；空则回退 CHAT_MODEL，并记 judge_independent=false
```

界面切换用的入口参数更明确（由 [`bootstrap/runtime.py`](../bootstrap/runtime.py) 调用）：

```python
from noteagent.llm.factory import create_chat_model_from_config

model = create_chat_model_from_config(
    provider="openai-compatible", model="qwen2.5",
    base_url="http://localhost:1234/v1", api_key="...",
)
```

`base_url` 是 langchain 1.x 的规范参数名，会落到客户端自身的 `base_url`；空的 `base_url` / `api_key` 不传给 SDK（DeepSeek 用官方默认地址）。"无需认证"的服务由调用方给占位 Key，见 `NO_AUTH_PLACEHOLDER`。

密钥走 `SecretStr`，不要 `print(settings.deepseek_api_key.get_secret_value())` 到日志。工厂只记 `provider` 与 `model`。

无真实 API 单测。连通性可用：

```bash
uv run python scripts/sdk_smoke.py
```
