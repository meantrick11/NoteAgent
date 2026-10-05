# 模型运行管理

管理当前模型/Agent/检索快照、请求租约、聊天模型启用和索引切换重建。

## 文件职责

| 文件 | 职责 |
|---|---|
| [ApplicationFlows/ModelRuntime/ModelRuntime.py](ModelRuntime.py) | 运行快照、租约、模型切换和重建协调 |

## 接口

ModelRuntimeService、RuntimeSnapshot；装配通过 RuntimeAssembler 接口注入。

## 依赖与约束

依赖 ModelSettings、ChatAgent、NoteStorage、NoteRetrieval 和 NoteAccessControl。ModelRuntime.py 的内部职责尚未进一步拆分。

## 验证

从仓库根运行：`uv run pytest Tests/Unit/TestModelManagement.py Tests/Integration/TestModelSettingsApi.py -q`。
