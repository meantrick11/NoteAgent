# web

轻量前端资源。Python 只负责读模板，业务规则不写在本目录。

## 包含模块

| 路径 | 作用 |
|------|------|
| [`templates/`](templates/README.md) | `home.html` 聊天页（会话侧栏 + SSE + 审批卡片） |
| [`static/`](static/README.md) | 预留 CSS/图片，尚未挂 StaticFiles |
| `__init__.py` | `TEMPLATES_DIR`、`read_home_html()` |

## 基础使用

```python
from noteagent.web import read_home_html

html = read_home_html()  # GET / 直接返回这段字符串
```

改 UI 只编辑 `templates/home.html`，刷新浏览器即可（后端若已启动不用为静态文案重启，但 SSE 逻辑改了要重启）。

```bash
uv run pytest tests/integration/test_app.py::test_home_serves_template -q
```
