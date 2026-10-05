# 笔记修改台账

记录正式笔记修改的来源、文件、版本、执行状态和幂等标识。

## 文件职责

| 文件 | 职责 |
|---|---|
| [BusinessModules/NoteStorage/ChangeJournal/NoteChangeJournal.py](NoteChangeJournal.py) | 笔记修改台账读写 |
| [BusinessModules/NoteStorage/ChangeJournal/NoteChangeModels.py](NoteChangeModels.py) | 本包负责的 ORM 记录 |

## 接口

MutationJournal.get/upsert/set_status；MutationRecord 为 ORM。

## 依赖与约束

使用 DatabaseAccess 的 Base 和 session；推进共享修改序号时更新 NoteAccessControl 的状态。台账与状态更新沿用同一事务。

## 验证

从仓库根运行：`uv run pytest Tests/Integration/TestNotesMutations.py -q`。
