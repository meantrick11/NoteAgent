# src

可安装的应用源码目录。与 `notes/`、`docs/`、`tests/`、`evals/` 分开：代码、正式笔记、契约文档、pytest、LLM 黄金集各放各的。

## 包含模块

| 路径 | 说明 |
|------|------|
| [`noteagent/`](noteagent/README.md) | 唯一 Python 包，包名 `noteagent` |

不要在仓库根再建 `agent/`、`router/` 这类业务目录。

## 基础使用

`pyproject.toml` 把 `src` 配进包路径。业务代码这样引用：

```python
from noteagent.bootstrap import Settings, build_container, create_app
```

脚本和测试同样 `import noteagent`，不要 `sys.path` 去指到某个 `.py`。

```bash
uv run pytest tests/unit/test_import.py -q
```
