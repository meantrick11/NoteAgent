# retrieval

把已有 Markdown 切块、向量化、写入 Chroma，再按查询返回片段。不改笔记文件、不改聊天状态。架构细则：[docs/architecture/retrieval.md](../../../docs/architecture/retrieval.md)。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `chunker.py` | `MarkdownChunker` | 默认 chunk 500、overlap 50，中文标点分隔 |
| `embedder.py` | `SentenceTransformerEmbedder` | 本地句向量；模型/缓存在 Settings |
| `vector_store.py` | `ChromaVectorStore` | PersistentClient upsert / query / 按 file_name 删除 / `has_file_name` |
| `service.py` | `RetrievalService`、`Embedder` Protocol | `index_note`（先删再写）、`delete_note`、`is_indexed`、`search` |
| `models.py` | `SearchHit` | `content`、`distance`、`metadata` |
| `__init__.py` | 再导出常用类型 | |

换模型只改 `.env`：`EMBEDDING_MODEL`、`EMBEDDING_CACHE_DIR`、`EMBEDDING_LOCAL_FILES_ONLY`。

## 基础使用

索引一篇笔记：

```python
from noteagent.retrieval.service import RetrievalService
# 或直接跑：uv run python scripts/index_notes.py Agent.md

n = service.index_note("Agent.md")   # 先删该文件旧点，再切块写入；返回 chunk 数
hits = service.search("注意力机制", top_k=3)
# hits[0].content / .distance / .metadata["file_name"]
```

索引步骤 INFO 在 [`IndexTrace`](../observability/index_trace.py)，不在 chunker/embedder。`RetrievalService` 只在步骤边界调用。文件：`var/logs/noteagent.log`。

聊天工具 `search_relative_from_chromadb` 内部就是 `search`，并把 `file_name` 注册为本轮 `source_id`。Documents 写盘与点「未索引」也走 `index_note` / `delete_note`，见 [frontend.md](../../../docs/architecture/frontend.md) §6。

测试用假 embedder，不加载真实模型：

```bash
uv run pytest tests/unit/test_chunker.py tests/integration/test_retrieval_service.py -q
```
