# 模型 HTTP

提供 /model-settings 下配置、探测、激活、向量切换与任务状态。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [HttpApi/ModelSettingsApi/ModelSettingsRoutes.py](ModelSettingsRoutes.py) | 路由与接口注册 |
| [HttpApi/ModelSettingsApi/ModelSettingsSchemas.py](ModelSettingsSchemas.py) | 请求响应结构 |

## 主要接口

ModelSettingsSchemas.py 显式导出验证后的命令与无密钥结果；内部存储对象不作 HTTP 响应。

## 依赖与约束

配置规则在 BusinessModules/ModelSettings，运行切换在 ApplicationFlows/ModelRuntime。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestModelSettingsApi.py -q
```
