# 前端托管

`WebRoutes.py` 提供页面路由；`templates/` 保存旧首页，`static/` 保存其静态资源。Vue 源码和测试位于仓库根目录的 `frontend/`；Vite 构建产物写入这里的 `dist/`，由 FastAPI 挂载到 `/ui-assets/`。`dist/` 是生成目录，不提交 Git。
