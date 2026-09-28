# web

前端资源与页面下发。Python 只负责挑页面、读产物，业务规则不写在本目录。

现行界面是 [`frontend/`](../../../frontend) 下的 Vue SPA，产物在 `dist/`（不入库，由
`npm --prefix frontend run build` 或镜像里的 Node 阶段生成），由 `create_app` 挂到 `/ui-assets/`。
`templates/` 与 `static/` 是旧实现，只在 `FRONTEND_MODE=legacy` 时下发，作为回退保留。

## 包含模块

| 路径 | 作用 |
|------|------|
| [`router.py`](router.py) | 页面白名单（`/`、`/assistant`、`/records`、`/library`、`/settings`、`/documents`）；按 `frontend_mode` 返回 SPA 外壳或旧模板；产物缺失时 503 |
| `dist/` | Vite 产物（构建生成，不入库） |
| [`templates/`](templates/README.md) | `home.html`：旧版 Chat / Documents 单页（legacy 回退） |
| [`static/`](static/README.md) | 旧版 `model-settings.css` / `model-settings.js`（legacy 回退） |
| `__init__.py` | `TEMPLATES_DIR`、`STATIC_DIR`、`DIST_DIR`、`read_spa_html()`、`read_home_html()` |

## 基础使用

```python
from noteagent.web import read_spa_html, read_home_html

read_spa_html()   # 有产物时返回 SPA 外壳，否则 None（页面路由据此返回 503）
read_home_html()  # 旧模板，legacy 模式用
```

改界面请改 [`frontend/`](../../../frontend)，不要改 `home.html`。页面白名单与 vue／legacy 的
分派在 [`router.py`](router.py)，布局说明见 [docs/architecture/frontend.md](../../../docs/architecture/frontend.md)。

```bash
uv run pytest tests/integration/test_frontend_routes.py -q
```
