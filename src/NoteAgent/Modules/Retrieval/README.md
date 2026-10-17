# Retrieval

`Service/` 提供检索、索引和维修；`Domain/Vo/` 保存检索结果，`Domain/Po/` 保存维修记录。`Engine/Chunking/` 负责 Markdown 切块，`Engine/Embedding/` 生成向量，`Engine/VectorStore/` 访问 Chroma。当前模块没有独立 HTTP 路由。
