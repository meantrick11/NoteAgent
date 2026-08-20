# docs

架构、决策、评估、外部摘录。实现契约以 architecture 基线为准，其它文档不能压过它。不要写密钥、不要放运行时数据。

## 包含模块

| 目录 | 说明 |
|------|------|
| [`architecture/`](architecture/README.md) | 现行知识工作流 + 画布；旧 OCR 方案仅历史 |
| [`decisions/`](decisions/README.md) | ADR，目前可空 |
| [`evaluations/`](evaluations/README.md) | 检索/Agent 评估集，目前可空 |
| [`references/`](references/README.md) | 外部文章摘录，不是实现契约 |
| [`plans/`](plans/README.md) | 给实现 Agent 的分步规格；产品边界仍以 architecture 为准 |

## 基础使用

写代码前先读：

```text
docs/architecture/knowledge-workflow-v1.md
```

画布文件可在 Cursor 里打开 `.canvas.tsx`。参考摘录只用来理解背景，冲突时以 `knowledge-workflow-v1.md` 为准。
