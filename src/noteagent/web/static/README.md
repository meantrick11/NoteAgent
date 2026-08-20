# static

CSS、JS、图片等静态文件。当前可以为空。不要提交密钥或用户笔记。

## 包含模块

暂无文件。以后若放 `app.css` 等，需在 FastAPI 里 `mount` StaticFiles（尚未接入）。现在样式写在 `templates/home.html` 的 `<style>` 里。

## 基础使用

有静态文件后再加类似：

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=...), name="static")
```

模板里用 `/static/app.css`。在接好之前不要假设 `/static` 能访问。
