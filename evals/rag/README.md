# rag evals

检索命中评测。第二期再填数据。跑检索脚本时只读本目录，不要扫整个 `notes/`。现行检索架构：[docs/architecture/retrieval.md](../../docs/architecture/retrieval.md)。

## 包含模块

尚无 `queries.jsonl`。计划字段：`query`、`expected_file`，可选 chunk 提示。

## 基础使用

有数据后再对 [`RetrievalService.search`](../../src/noteagent/retrieval/README.md) 算是否命中文件名。与 [`../prompt/`](../prompt/README.md) 分开，不要混进同一 JSONL。
