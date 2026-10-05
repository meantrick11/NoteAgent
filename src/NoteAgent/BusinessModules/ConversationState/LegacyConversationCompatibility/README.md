# 旧会话兼容

旧 messages 表存取、数据导入和旧审批兼容。

## 文件索引

| 文件或目录 | 职责 |
|---|---|
| [BusinessModules/ConversationState/LegacyConversationCompatibility/LegacyConversationMigration.py](LegacyConversationMigration.py) | 旧历史导入 |
| [BusinessModules/ConversationState/LegacyConversationCompatibility/LegacyDraftReview.py](LegacyDraftReview.py) | 旧审批兼容 |
| [BusinessModules/ConversationState/LegacyConversationCompatibility/LegacyConversationStore.py](LegacyConversationStore.py) | 配置或旧消息存储 |

## 主要接口

LegacyConversationStore.py 提供 ConversationStore；LegacyConversationMigration.py 提供 ConversationMigrator；LegacyDraftReview.py 保留旧审批。

## 依赖与约束

侧栏元数据 CRUD 暂时复用 store；新正文和草稿通过 ConversationService。旧历史迁移完成前保留。

## 验证

从仓库根运行：

```powershell
uv run pytest Tests/Unit/TestChatHistory.py Tests/Unit/TestDrafts.py Tests/Integration/TestConversationMigration.py -q
```
