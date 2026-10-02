# 批准后自动索引

> 本日实现规格。切块器、embedding 模型、Chroma 均不更换。无入库开关、无 PDF、无出处 UI。

**Goal:** 人审写盘成功后，该 `file_name` 的向量与磁盘正文一致，下一轮 `search` 能命中。

**做法:** `commit_review` 成功后调用 `RetrievalService`。create/append/replace：按 `file_name` 删旧点，再读全文切块、向量化、upsert。delete：只删点。索引失败只打日志，不回滚 Markdown、不改变 `written`。

**不改:** `MarkdownChunker` 参数、`EMBEDDING_MODEL` 默认、search 工具返回值、前端。

## 文件

| 文件 | 改动 |
|------|------|
| `vector_store.py` | `delete_by_file_name` |
| `service.py` | `delete_note`；`index_note` 先删再写 |
| `drafts.py` | 可选 `retrieval`；写盘成功后同步 |
| `agent.py` / `app.py` | 注入 `retrieval` |
| 测试与 README / architecture 现状句 | 与代码对齐 |

## 验收

- 批准 create 后，假 embedding 下 search 能命中该文件。
- 同一文件 replace 变短后，旧独有句子搜不到。
- 批准 delete 后，该文件向量消失。
- reject 不碰 Chroma。
- 索引抛错时文件仍在，HTTP/返回仍是 `written`。
