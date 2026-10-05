# 页面与资源

下发 Vue SPA，托管 /ui-assets，保留 FRONTEND_MODE=legacy。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/WebFrontend/WebRoutes.py](WebRoutes.py) | 路由与接口注册 |
| [static/](static/README.md) | 旧页面使用的 JavaScript 和 CSS |
| [templates/](templates/README.md) | 旧页面模板 |

## 主要接口

WebRoutes.py 管理页面白名单；__init__.py 管理 HTML 和资源路径。

## 依赖与约束

Vite 输出到 dist；templates/static 维护显式旧版回退。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestFrontendRoutes.py -q
```
