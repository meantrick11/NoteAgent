# static

旧版前端的 CSS / JS，**只在 `FRONTEND_MODE=legacy` 时使用**。不要提交密钥或用户笔记。

现行界面的等价物是 [`frontend/src/features/models/`](../../../../frontend/src/features/models)：
`ModelQuickControls.vue` + `ChatProfiles.vue` + `EmbeddingSettings.vue`，状态在
`features/models/store.ts`。改界面请改那边。

`create_app` 里 `app.mount("/static", StaticFiles(directory=STATIC_DIR))`，所以旧模板可以直接引用。

## 包含模块

| 文件 | 作用 |
|------|------|
| `model-settings.css` | 旧版输入框下方两个模型入口：工具栏、向上展开的弹层、表单、进度与错误样式 |
| `model-settings.js` | 旧版 `ModelSettings`：状态轮询、聊天 profile 表单与激活、向量候选与重建进度 |

## 基础使用

由 `templates/home.html` 引用，`create_app` 挂载 `/static`：

```html
<link rel="stylesheet" href="/static/model-settings.css">
...
<script src="/static/model-settings.js"></script>
```

服务端返回的字符串一律用 `textContent` 渲染，禁止拼进 `innerHTML`——这条在 Vue 版里等价为
不使用 `v-html` 渲染任何服务端字符串（助手正文是 Markdown，走 `marked`，与旧版一致）。

删除这套旧实现另开清理任务；在 vue 模式成为默认之后，它只在回退时被加载。
