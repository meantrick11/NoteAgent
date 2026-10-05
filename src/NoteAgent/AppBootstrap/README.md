# 装配与生命周期

构造依赖、装配图、创建应用、启动续处理与释放资源。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [AppBootstrap/ChatAgentFactory.py](ChatAgentFactory.py) | 图装配与隔离运行辅助 |
| [AppBootstrap/HttpApp.py](HttpApp.py) | 应用创建 |
| [AppBootstrap/ContainerAssembly.py](ContainerAssembly.py) | 依赖容器 |
| [AppBootstrap/AppLifespan.py](AppLifespan.py) | 生命周期 |
| [AppBootstrap/RuntimeAssembler.py](RuntimeAssembler.py) | 模型/检索/Agent 装配 |
| [AppBootstrap/AppSettings.py](AppSettings.py) | 启动配置 |

## 主要接口

ContainerAssembly.py: build_container；HttpApp.py: create_app；AppLifespan.py: 生命周期；RuntimeAssembler.py: 模型运行装配器。

## 依赖与约束

连接所有层。项目根、环境变量和外部启动命令保持不变。agent_factory 提供生产与隔离运行共用的装配。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestAppContainer.py Tests/Unit/TestSettings.py Tests/Integration/TestFrontendRoutes.py -q
```
