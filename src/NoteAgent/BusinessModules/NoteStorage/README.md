# 正式笔记

Markdown 文件、路径校验、正式修改和影子 Git。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/NoteStorage/NoteChanges.py](NoteChanges.py) | 正式写入 |
| [BusinessModules/NoteStorage/MarkdownRepository.py](MarkdownRepository.py) | 文件存取 |
| [BusinessModules/NoteStorage/NoteVersions.py](NoteVersions.py) | 影子 Git |

## 主要接口

NoteMutationService.apply/restore 为正式修改接口；repository 负责正文，versions 负责版本。

## 依赖与约束

ChangeJournal/MutationJournal 维护笔记修改台账；NoteAccessControl 提供访问互斥；index_repairs 提供索引同步接口；审批和 Library 共用写入流程。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestNoteRepository.py Tests/Integration/TestNotesMutations.py Tests/Integration/TestNotesVersions.py -q
```

## 修改台账

[ChangeJournal](ChangeJournal/README.md) 保存笔记修改来源、版本和执行状态；访问互斥由 TechnicalSupport/NoteAccessControl 提供。
