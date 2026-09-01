# evaluations

人工 / LLM 黄金集已迁到仓库根目录 **[evals/](../../evals/README.md)**。

## 包含模块

本目录不再放 JSONL。数据在：

| 路径 | 内容 |
|------|------|
| [evals/prompt/](../../evals/prompt/README.md) | 13 条提示词/笔记质量用例 |
| [evals/rag/](../../evals/rag/README.md) | 检索（空） |
| [evals/agent/](../../evals/agent/README.md) | 工具轨迹（复用 prompt behavior 条） |

## 基础使用

打分步骤见 [evals/README.md](../../evals/README.md)。`tests/` 仍只跑无网络单元测试。
