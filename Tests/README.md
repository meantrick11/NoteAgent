# Tests

锁定当前行为：路径安全、切块、工具不写盘、审批落盘、会话历史、上下文压缩、HTTP/SSE 冒烟。不要把真实 API key 写进用例。默认不加载真实 embedding / LLM。

提示词与笔记质量的黄金集在 [`evals/`](../evals/README.md)，准则在 [`evals/criteria/`](../evals/criteria)，**都不是**本目录；不要把要调真实聊天模型的用例放进 pytest。

## 包含模块

| 目录 | 说明 |
|------|------|
| [`Unit/`](Unit/README.md) | 无网络、无真实模型 |
| [`Integration/`](Integration/README.md) | 临时目录、假 Agent、假 embedding + 临时 Chroma |
| [`E2e/`](E2e/README.md) | 预留，尚无用例 |

`pyproject.toml` 里 `pythonpath = [".", "src", "Tests", "Tools"]`，测试里直接 `import NoteAgent`。

## 基础使用

```bash
uv run pytest -q
uv run pytest Tests/Unit -q
uv run pytest Tests/Integration -q
```

## 源码组织与测试归属

测试按验证方式划分，业务对应关系见 [源码导航](../src/NoteAgent/README.md)。源码移动后继续覆盖原 HTTP 路径、事务、checkpoint 和写盘行为。

- 结构约束：unit/TestSourceOrganization.py，检查五个源码入口、业务与 HTTP 隔离、ORM 注册及前端资源路径。
- 模型探测回归：unit/TestModelProbes.py，覆盖不支持探测时的结果构造。
- 评测实现位于 [Tools/NoteAgentEvals](../Tools/NoteAgentEvals/README.md)，pytest 的 Tools 搜索路径供评测测试导入。
- 数据库集成测试需要可连接的 DATABASE_URL，fixture 使用隔离 schema；日常无数据库验证可先运行 Tests/unit。

## 测试发现与文件命名

测试文件采用 PascalCase，例如 Unit/TestSourceOrganization.py；pyproject.toml 配置 python_files = ["Test*.py"]。测试函数继续采用 pytest 的 test_ 前缀，conftest.py 保留固定名称。
