# architecture

现行架构基线与可视化。**实现以 `knowledge-workflow-v1.md` 为准。**

## 包含模块

| 文件 | 作用 |
|------|------|
| `knowledge-workflow-v1.md` | 知识子系统：提案、审批、索引、检索给文章 Agent |
| `noteagent-architecture.canvas.tsx` | 结构画布 |
| `noteagent-system-workflow.canvas.tsx` | 流程画布 |
| `architecture.md` | 早期屏幕/OCR 方案，历史参考 |
| `DESIGN.md` | 早期设计，与当前代码不一致时忽略 |

## 基础使用

给人和编码 Agent 的主文档：

```text
docs/architecture/knowledge-workflow-v1.md
```

当前仓库 MVP 只覆盖其中「对话 → 草稿审批 → 本地 Markdown」；自动索引、引用 API、URL 抓取尚未做。
