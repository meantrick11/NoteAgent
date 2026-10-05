# 检索

切块、向量化、向量库查询、结果和索引维护。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/NoteRetrieval/MarkdownChunker.py](MarkdownChunker.py) | 切块 |
| [BusinessModules/NoteRetrieval/TextEmbedder.py](TextEmbedder.py) | 向量化 |
| [BusinessModules/NoteRetrieval/EmbeddingInstructions.py](EmbeddingInstructions.py) | embedding 指令和指纹 |
| [BusinessModules/NoteRetrieval/MarkdownSections.py](MarkdownSections.py) | 正文和章节处理 |
| [BusinessModules/NoteRetrieval/RetrievalModels.py](RetrievalModels.py) | ORM 或业务数据结构 |
| [BusinessModules/NoteRetrieval/NoteRetrievalService.py](NoteRetrievalService.py) | 模块主要接口 |
| [BusinessModules/NoteRetrieval/ChromaVectorStore.py](ChromaVectorStore.py) | Chroma 存取 |
| [IndexRepair/](IndexRepair/README.md) | 索引维修任务、重试与维修记录 ORM |

## 主要接口

RetrievalService 提供索引与查询，IndexRepair/IndexRepairService.py 管理索引维修。

## 依赖与约束

读取正式笔记，collection 按指纹隔离；陈旧索引经维修后才可返回。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestRetrievalService.py Tests/Unit/TestEmbedder.py -q
```
