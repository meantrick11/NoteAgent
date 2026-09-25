# static

CSS、JS 等静态文件。不要提交密钥或用户笔记。

`create_app` 里 `app.mount("/static", StaticFiles(directory=STATIC_DIR))`，所以模板可以直接引用。

## 包含模块

| 文件 | 作用 |
|------|------|
| `model-settings.css` | 输入框下方两个模型入口：工具栏、向上展开的弹层、表单、进度与错误样式 |
| `model-settings.js` | `ModelSettings`：状态轮询、聊天 profile 表单与激活、向量候选与重建进度 |

## 基础使用

在 `templates/home.html` 里引用：

```html
<link rel="stylesheet" href="/static/model-settings.css">
...
<script src="/static/model-settings.js"></script>
```

页面接线（已在 `home.html` 完成）：先 `ModelSettings.onBusyChange(applyModelBusyState)` 再 `ModelSettings.init()`；发送按钮禁用状态用 `!ModelSettings.canSend() || 空输入` 计算，维护窗口只叠加、不覆盖原有判断。

服务端返回的字符串一律用 `textContent` 渲染，禁止拼进 `innerHTML`。
