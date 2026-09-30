# 业务需求与功能映射

本表把既有文档中的业务环节、需求主题和功能入口连起来。它是导航索引，功能细节及验收条件以 [需求索引](requirements.md)所指向的原文为准，当前状态以 [路线图 §1.3](roadmap.md#13-当前状态与证据边界) 为准。

| 业务环节 | 需求主题 | 对应功能或设计入口 |
|---|---|---|
| 指定内容并整理草稿 | REQ-001、REQ-002、REQ-003、REQ-007 | 聊天、上下文管理、草稿生成；[现行架构](../../../architecture/architecture.md) |
| 核对、确认和保存材料 | REQ-002、REQ-005、REQ-010 | 草稿审批与保存；[业务规则](business-architecture.md)、[现行架构](../../../architecture/architecture.md) |
| 找回、核对来源并复用 | REQ-004、REQ-006、REQ-008、REQ-017 | 索引、检索、引用和再加工；[检索架构](../../../architecture/retrieval.md) |
| 扩展内容来源 | REQ-009、REQ-013、REQ-014、REQ-015、REQ-016 | 网页、文件、图片、音频、视频候选能力；[路线图](roadmap.md) |
| 统一入口与整理方式 | REQ-011、REQ-012 | Vue 页面、导航、设置与整理方案；[前端设计](frontend-architecture.md)、[设置设计](settings-architecture.md) |

一条需求可关联多个功能；功能已存在不表示相关业务需求已经验收。未来正式选定迭代范围时，应为本轮需求补全具体功能、实施计划与验证链接。
