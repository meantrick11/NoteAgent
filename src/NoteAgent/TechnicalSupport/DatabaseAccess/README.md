# 数据库基础设施

SQLAlchemy Base、Engine、Session factory 和 ORM 注册。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [TechnicalSupport/DatabaseAccess/OrmBase.py](OrmBase.py) | 共享 Base |
| [TechnicalSupport/DatabaseAccess/DatabaseEngine.py](DatabaseEngine.py) | 数据库连接 |
| [TechnicalSupport/DatabaseAccess/ModelRegistry.py](ModelRegistry.py) | ORM 注册 |

## 主要接口

load_all_models 注册 ConversationState、NoteStorage/ChangeJournal、ConversationRecovery、NoteRetrieval/IndexRepair 和 NoteAccessControl 的表。

## 依赖与约束

Base 不导入业务模块，registry 单独注册 metadata；沿用现有 Alembic 迁移链。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestSourceOrganization.py Tests/Integration/TestPostgresSchema.py -q
```
