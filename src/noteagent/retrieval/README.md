# retrieval

把已有 Markdown 切块、向量化、写入 Chroma，再按查询返回片段。不改笔记文件、不改聊天状态。

## 包含模块

| 文件 | 模块 | 作用 |
|------|------|------|
| `chunker.py` | `MarkdownChunker` | 默认 chunk 500、overlap 50，中文标点分隔 |
| `embedder.py` | `SentenceTransformerEmbedder` | 本地句向量；模型/缓存在 Settings |
| `vector_store.py` | `ChromaVectorStore` | PersistentClient upsert / query |
| `service.py` | `RetrievalService`、`Embedder` Protocol | `index_note`、`search` |
| `models.py` | `SearchHit` | `content`、`distance`、`metadata` |
| `__init__.py` | 再导出常用类型 | |

换模型只改 `.env`：`EMBEDDING_MODEL`、`EMBEDDING_CACHE_DIR`、`EMBEDDING_LOCAL_FILES_ONLY`。

## 基础使用

索引一篇笔记：

```python
from noteagent.retrieval.service import RetrievalService
# 或直接跑：uv run python scripts/index_notes.py Agent.md

n = service.index_note("Agent.md")   # 返回 chunk 数
hits = service.search("注意力机制", top_k=3)
# hits[0].content / .distance / .metadata["file_name"]
```

聊天工具 `search_relative_from_chromadb` 内部就是 `search`。检索黄金集（尚未填）预定在 [`evals/rag/`](../../../evals/rag/README.md)，与 `tests/` 分开。

测试用假 embedder，不加载真实模型：

```bash
uv run pytest tests/unit/test_chunker.py tests/integration/test_retrieval_service.py -q
```
