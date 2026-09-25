# web

轻量前端资源。Python 只负责读模板，业务规则不写在本目录。

## 包含模块

| 路径 | 作用 |
|------|------|
| [`templates/`](templates/README.md) | `home.html`：Chat / Documents。布局见 [docs/architecture/frontend.md](../../../docs/architecture/frontend.md) |
| [`static/`](static/README.md) | `model-settings.css` / `model-settings.js`；由 `create_app` 挂到 `/static` |
| `__init__.py` | `TEMPLATES_DIR`、`STATIC_DIR`、`read_home_html()` |

## 基础使用

```python
from noteagent.web import read_home_html

html = read_home_html()  # GET / 直接返回这段字符串
```

改 UI 只编辑 `templates/home.html`，刷新浏览器即可。用户气泡换行是否可见，看 `.msg-row.user .msg-body` 的 `pre-wrap`。

```bash
uv run pytest tests/integration/test_app.py::test_home_serves_template -q
```
