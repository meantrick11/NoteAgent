# 入库 Job（设想，非现行系统）

> 现行对话 → 提案 → 人审 → `notes/` 见 [architecture.md](../architecture/architecture.md) 与 [chat-tools.md](../architecture/chat-tools.md)。  
> 本文只保留尚未写入代码的 IngestionJob / URL 源 / 自动索引设想，供以后做入库时对照。不要按本文理解当前进程。

屏幕采集旧设计：[../architecture/DESIGN.md](../architecture/DESIGN.md)。

---

设想中 NoteAgent 还要：从明确 URL 或搜索结果取来源、独立 Reviewer、审批后自动索引、带引用的 Retrieval。对话路径已经在架构书里。

原则仍是：LLM 只出提案；写目录、写文件、改索引由确定性代码执行。

## 工作流

```text
用户输入（中文对话 / URL / 搜索主题）
→ 消息先写入 PostgreSQL
→ Agent Router：普通聊天 | 笔记任务 | 知识问答
→ 笔记任务：Source Adapter 形成 SourceBundle
    Direct：规范化所选消息
    URL：Fetch 指定页
    搜索：规划查询 → 筛选来源 → Fetch 入选页
→ 分类匹配或提出新分类
→ Note Composer：source-only 生成中文结构化草稿
→ 程序校验 + 独立 Reviewer
→ 用户审批 KnowledgeChangeSet
    退回 → Composer
    批准 → Executor 写入 Markdown + 版本
→ Index Job：H2/H3 章节感知 Chunk
→ Embedding → Chroma 增量 upsert
→ Retrieval API
```

每个 IngestionJob：

```text
SUBMITTED → FETCHED → CLASSIFIED → DRAFTED
→ PENDING_REVIEW → APPROVED → COMMITTED
→ INDEX_PENDING → INDEXED
```

失败单独记录（如 `FETCH_FAILED`、`INDEX_FAILED`），从对应阶段重试。Markdown 已提交但索引失败：只重试索引，不重新审批，不回滚笔记。

## 存储（设想）

| 存储 | 职责 |
|------|------|
| PostgreSQL | 会话、消息、IngestionJob、审批、分类、偏好、审计 |
| Markdown | 正式知识事实源 |
| Chroma | 由已审批 Markdown 派生，可删除重建 |
| 网页正文 | 工作流期间临时使用，写入成功后丢弃 |

稳定身份：`ingestion_id`、`note_id`、`note_version`、`category_id`、`source_content_hash`、`chunk_id`、`chunk_hash`。路径不能当唯一 ID。

## 质量与检索（设想）

- 一篇来源一篇正式 Markdown；统一 frontmatter。
- source-only；推论标明；英文页由 Composer 写成中文，不加专用翻译模型。
- 三层门：程序校验 → 独立 Reviewer → 用户审批。
- 检索：阈值、每篇最多 2 chunk、邻居展开、引用字段、章节感知切块。

Collector 无写文件权限。网页是数据不是指令。Job.status 以业务表为准。

画布（设想流程，不是运行时）：[noteagent-architecture.canvas.tsx](../architecture/noteagent-architecture.canvas.tsx)、[noteagent-system-workflow.canvas.tsx](../architecture/noteagent-system-workflow.canvas.tsx)。
