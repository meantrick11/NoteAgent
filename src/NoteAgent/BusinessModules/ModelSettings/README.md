# 模型配置与连接

配置、凭据合并、候选目录、客户端和能力探测。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/ModelSettings/ModelCatalog.py](ModelCatalog.py) | 模型候选 |
| [BusinessModules/ModelSettings/ModelClients.py](ModelClients.py) | 客户端工厂 |
| [BusinessModules/ModelSettings/ModelContracts.py](ModelContracts.py) | 调用契约和状态结构 |
| [BusinessModules/ModelSettings/ModelErrors.py](ModelErrors.py) | 错误分类与转换 |
| [BusinessModules/ModelSettings/ModelProbes.py](ModelProbes.py) | 连接和能力测试 |
| [BusinessModules/ModelSettings/ModelProfiles.py](ModelProfiles.py) | 配置与凭据合并 |
| [BusinessModules/ModelSettings/ModelSettingsStorage.py](ModelSettingsStorage.py) | 配置或旧消息存储 |

## 主要接口

profiles.merge_candidate、probes.probe_model、ModelSettingsStore 提供配置规则、探测、原子保存。

## 依赖与约束

运行快照、租约、激活和重建发布由 ApplicationFlows/ModelRuntime/ModelRuntime.py 管理。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestModelSettingsStore.py Tests/Unit/TestModelCatalog.py Tests/Unit/TestLlmFactory.py Tests/Unit/TestModelManagement.py Tests/Unit/TestModelProbes.py -q
```
