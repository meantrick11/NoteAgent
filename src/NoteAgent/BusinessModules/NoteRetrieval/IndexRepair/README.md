# 索引同步与维修

按文件记录 pending/ready/failed，核对正文 hash 与配置指纹。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/NoteRetrieval/IndexRepair/IndexRepairModels.py](IndexRepairModels.py) | ORM 或业务数据结构 |
| [BusinessModules/NoteRetrieval/IndexRepair/IndexRepairService.py](IndexRepairService.py) | 按文件索引维修 |

## 主要接口

IndexRepairService 维修索引，IndexRepairModels.py 定义 index_repairs。

## 依赖与约束

依赖笔记读取和数据库；恢复流程调用同一维修接口。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Integration/TestIndexRepairs.py -q
```
