# tests

锁定当前行为：路径安全、切块、工具不写盘、审批落盘、会话历史、上下文压缩、HTTP/SSE 冒烟。不要把真实 API key 写进用例。默认不加载真实 embedding / LLM。

## 包含模块

| 目录 | 说明 |
|------|------|
| [`unit/`](unit/README.md) | 无网络、无真实模型 |
| [`integration/`](integration/README.md) | 临时目录、假 Agent、假 embedding + 临时 Chroma |
| [`e2e/`](e2e/README.md) | 预留，尚无用例 |

`pyproject.toml` 里 `pythonpath = ["src"]`，测试里直接 `import noteagent`。

## 基础使用

```bash
uv run pytest -q
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```
