# archive

被替代、废弃的设计与附属材料。这里的内容**不是**现行实现，也**不是**有效需求；只保留历史正文与替代关系，供以后重读当时的权衡。

维护规则：

- 归档时保留正文含义，不把历史全文改写成新设计。
- 每份归档稿头部写明：历史状态、核对日期、具体失效假设、有效替代入口。
- 替代旧设计时必须在两端都加上替代链接：原文留跳转页，新位置写清来源。
- 归档不等于删除。被取代的旧稿即使“只遗留一个跳转页”，历史正文也保留在本目录内。

## designs

| 文件 | 内容 | 历史状态 | 有效替代入口 |
|---|---|---|---|
| [screen-audio-early-design.md](./designs/screen-audio-early-design.md) | 屏幕截图 + 系统音频转写方案（MVP 分层、pHash 变化检测、VAD 分段、三 Tool 拆分、滑动上下文） | 已被替代；仓库无 `capture/screen.py`、无 Whisper 主循环 | 现行系统 [architecture.md](../../architecture/architecture.md)；多模态范围 [versions.md](../roadmap.md) V3.4 |
| [ingestion-job-early-design.md](./designs/ingestion-job-early-design.md) | IngestionJob 状态机、URL/搜索来源、自动索引、Reviewer 设想 | 已被替代；从未写入代码，其中旧假设已失效 | 业务目标 [business-architecture.md](../business-architecture.md)；阶段要求 [versions.md](../roadmap.md) |
| [noteagent-architecture.canvas.tsx](./designs/noteagent-architecture.canvas.tsx) | 入库设想画布（Cursor 画布，非运行时） | 已被替代；仅 import `cursor/canvas`，仓库内无渲染器、无代码引用 | 同上 |
| [noteagent-system-workflow.canvas.tsx](./designs/noteagent-system-workflow.canvas.tsx) | 整体系统工作流程画布（含 Index Job、LangGraph checkpoint 设想） | 已被替代；同上 | 同上 |

迁移记录：原 `docs/architecture/DESIGN.md` 与 `docs/plans/draft-generation.md` 已在本目录保留正文，原路径只留跳转页；两个画布从 `docs/architecture/` 移入本目录（2026-09-27）。详见 [整理记录](../../plans/2026-09-27-documentation-audit.md)。
