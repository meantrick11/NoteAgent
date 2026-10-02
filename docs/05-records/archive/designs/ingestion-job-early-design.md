# 入库 Job（设想，非现行系统）

> **历史设计，已被替代（2026-09-27 归档核对）。** 本文是「IngestionJob / URL 源 / 自动索引」的产品设想，从未写入代码，不作为实施规格。以下旧假设不再作为约束：① 一篇来源一篇 Markdown；② 成功后丢弃全部网页正文；③ 强制独立 Reviewer；④ Collector 不能写任何文件。
>
> - **已部分落地：** 审批后同步索引、草稿与人审链路已在现行系统实现。目标允许多来源关联、保留必要核对依据；Reviewer 须经评测证明收益；Collector 可在授权范围内保存来源，但不提交正式材料。
> - **有效替代入口：** 业务目标 [business-architecture.md](../../../../../NoteAgent-docs/docs/01-business/BIZ-001-业务愿景与材料管理.md)；阶段范围与验收 [versions.md](../../../../../NoteAgent-docs/docs/02-requirements/REQ-CATALOG-产品能力与验收要求.md)；现行系统 [architecture.md](../../../01-architecture/architecture.md)、[chat-tools.md](../../../02-api/chat-tools.md)；屏幕采集旧稿 [screen-audio-early-design.md](screen-audio-early-design.md)；画布 [noteagent-architecture.canvas.tsx](../../../07-assets/archive/noteagent-architecture.canvas.tsx)、[noteagent-system-workflow.canvas.tsx](../../../07-assets/archive/noteagent-system-workflow.canvas.tsx)。

> 下文保留归档时的原设想正文，其中「一篇来源一篇 Markdown」「成功后丢弃网页正文」「强制 Reviewer」「Collector 不能写任何文件」等表述已被上面的说明取代。

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

画布（设想流程，不是运行时）：[noteagent-architecture.canvas.tsx](../../../07-assets/archive/noteagent-architecture.canvas.tsx)、[noteagent-system-workflow.canvas.tsx](../../../07-assets/archive/noteagent-system-workflow.canvas.tsx)。
