# model_management

输入框下方右侧两个入口的后端：聊天 profile 配置、本地向量候选、以及"切换后界面 / 实际请求 / 索引 / 重启状态一致"的运行管理。

不装配模型、不扫描任意路径：装配由 bootstrap 注入的 `RuntimeAssembler` 完成，向量候选只枚举受支持清单。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `schemas.py` | `ChatProfile`、`ChatProfileIn`、`ChatProfileOut`、`StoredModelSettings`、`EmbeddingJobRecord` | 请求/响应/内部结构；内部结构持有明文 Key，`ChatProfileOut` 只给 `has_api_key` |
| `store.py` | `ModelSettingsStore`、`default_chat_profile`、`initial_stored_settings` | `MODEL_SETTINGS_DIR/settings.json`：带 revision 的原子写、active 指针、corrupt 配置诊断 |
| `catalog.py` | `list_candidates`、`inspect_model`、`KNOWN_EMBEDDING_MODELS` | 只看本地 HF 缓存：可用 / 缓存不完整 / 不支持；不下载、不加载 |
| `service.py` | `ModelRuntimeService`、`RuntimeSnapshot` | 运行快照、操作门禁、维护窗口、聊天测试与激活事务、向量重建任务 |
| `router.py` | `router`、`chat_lease`、`write_lease` | `/model-settings*`；并导出请求级租约依赖给 chat / notes 路由 |
| `__init__.py` | 再导出公开符号 | `from noteagent.model_management import ChatProfile` |

## 基础使用

```python
from noteagent.model_management import ModelSettingsStore, ModelRuntimeService
from noteagent.bootstrap.runtime import BootstrapAssembler

assembler = BootstrapAssembler(settings, notes, drafts, history)
runtime = ModelRuntimeService(
    settings=settings,
    store=ModelSettingsStore(settings.model_settings_dir),
    notes=notes,
    assembler=assembler,
)
runtime.initialize()          # 读持久 active，装配运行对象；索引坏了只报不可用
with runtime.chat() as snap:  # 一次请求内固定用同一套对象
    agent = snap.chat_agent
```

- **配置优先级**：`settings.json` 里的持久 active 优先于 `.env` 的 `CHAT_MODEL` / `EMBEDDING_MODEL`；文件不存在时用环境生成初始配置，且启动不写盘。
- **凭据**：`.env` 的 Key 只以 `credential_source="env"` 引用，不复制进配置文件；界面上填写的 Key 才落盘。响应、日志、前端存储都不回显 Key。
- **门禁**：`read()` 只读、维护期间可用；`write()` / `chat()` 在维护窗口内抛 `BusyError`（HTTP 409），并在释放前计数，保证窗口打开时不吞掉正在进行的请求。
- **单进程限制**：维护窗口只约束本进程。窗口内不要同时跑 `scripts/index_notes.py`。
- **同源校验**：带凭据的写接口（`chat/test`、profiles、activate、embedding/switch）会拒绝 `Origin` 与 `Host` 不一致的请求（403）。**没有 `Origin` 头的请求一律放行**——curl、服务端脚本、测试客户端不受浏览器跨站规则约束，也不启用任意站点 CORS。
- **Docker**：`docker-compose.yml` 单独挂载 `model_settings` 卷到 `/app/var/model_settings`（不覆盖整个 `/app/var`，否则会隐藏镜像里预下载的模型）。候选列表只反映**容器内**能看到的缓存；宿主上另外下载的模型不会自动出现，需要时把宿主缓存目录挂进来（只读即可，例如 `-v D:/develop/aidevelop/transformer_models:/app/var/models:ro`），并把 `EMBEDDING_CACHE_DIR` 指到同一路径。

```bash
uv run pytest tests/unit/test_model_settings_store.py tests/unit/test_model_catalog.py \
  tests/unit/test_model_management.py tests/integration/test_model_settings_api.py -q
```

HTTP 契约、错误结构与浏览器验收项见 [docs/plans/2026-09-25-model-switching-ui.md](../../../docs/plans/2026-09-25-model-switching-ui.md)；前端交互见 [docs/architecture/frontend.md](../../../docs/architecture/frontend.md) §3.1；向量重建语义见 [docs/architecture/retrieval.md](../../../docs/architecture/retrieval.md) §7.1。
