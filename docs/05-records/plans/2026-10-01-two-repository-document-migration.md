# 双仓库文档迁移计划与记录

**Goal:** 将上层正文迁入同级 NoteAgent-docs，项目内文档按用途组织并跟随代码。

**Architecture:** 上层业务/需求/目标设计按稳定 ID 独立版本维护；代码内只保留实现说明、操作步骤与历史执行记录。迁移保持旧 Tag 和证据，新增回退方案为 review。

**Tech Stack:** Markdown、Git、本地链接校验。

**Spec:** 用户 2026-10-01 指定的两套文档治理规则；上层 GOV-001/ADR-001。

## 约束

- 不修改运行代码、notes、数据库和模型配置。
- 不改变 docs/references、docs/roadmap、TODO 的个人内容。
- 不覆盖 docs-v1.5.0/docs-v1.5.1，不把迁移冒充发布或冻结基线。
- 不改写旧验收数字和 run 身份；目标方案不冒充当前实现。

## 任务与文件

1. 导入 docs/product/versions/1.5.0 中业务、需求、前端、设置、映射和交付正文到 NoteAgent-docs/docs 对应用途目录；建立来源记录、元数据与文末变更记录。
2. 建立 NoteAgent-docs/docs/00-governance 的规范、目录和追溯矩阵，新增 REQ-018、ARC-001、ADR-002、CR-2026-001 及模块/接口/数据/验收/发布约束。
3. 将本库 docs/architecture、guides、plans、product/archive 按 00-overview～07-assets 移动，更新 README、源码 README 和 evals 中的 Markdown 导航链接。历史计划文字性的旧路径仍属于历史上下文。
4. 校验双库本地链接、上层 ID/元数据、正文内容保留与受保护文件哈希、git diff --check；初始化上层仓库并首次提交。原始来源提交 59c23210cf85138d5a851771f1c8d5f74e652b0f，旧文档基线 dd23d885cbc6536f9e8e1db86dca358ed332db21。

## 执行结果

- [x] 上层仓库建立于 `D:\develop\project\selfproject\agentbuild\NoteAgent-docs`，默认分支 `main`，首次提交 `7920169e44a0e6d3e3215916c71fcdc0e173b7e2`，共 29 个文件，工作区干净；未配置远程或推送。
- [x] 原产品正文迁入上层 `docs/`，增加稳定文档 ID、独立版本、来源信息与文末记录。REQ-001～017 仍作为需求条目 ID，正文集中于 REQ-CATALOG，并由 REQ-INDEX 定位，避免重复正文。
- [x] 代码库正式文档按 `00-overview`～`07-assets` 整理。旧 plans 进入 `05-records/plans`；旧设计进入 `05-records/archive`；画布进入 `07-assets/archive`。README、源码/测试 README 和评测文档只调整导航链接。
- [x] 校验 104 份 Markdown 的本地链接，无缺失目标；8 份上层导入正文去除新增治理头/记录、归一化链接目标后，与导入前正文相同。
- [x] 6 份 `docs/references`、`docs/roadmap` 个人文件 SHA-256 保持一致；TODO、CONTEXT 和 CLAUDE 未改动。用户原先已有的个人文件差异保留。
- [x] 本次范围内 `git diff --check` 通过。检查排除未触碰的个人 references/roadmap；个人 `思考.md` 原有尾空格未修正。
- [x] 运行代码未改动，未执行运行测试。旧 `docs-v1.5.1` 仍指向 `dd23d885cbc6536f9e8e1db86dca358ed332db21`，没有覆盖 Tag 或创建新软件发布/冻结快照。

代码仓库此次迁移保留在工作区中，尚未提交。迁移前副本及逐文件清单保存在被 Git 忽略的 `var/doc-migration-2026-10-01/backup-code` 和 `manifest.json`，校验结果在同目录 `verification.json`。

checkpoint 与整体回退实现需在技术方案评审后另写实施计划。本记录不授权静默覆盖其他会话对共享笔记的修改。

## 后续评审入口

- [CR-2026-001：变更范围与影响分析](../../../../NoteAgent-docs/docs/09-decisions/CR-2026-001-文档治理与整体回退机制迁移.md)
- [REQ-018：历史编辑与整体回退](../../../../NoteAgent-docs/docs/02-requirements/REQ-018-历史消息编辑与整体回退.md)
- [ADR-002：checkpoint 与影子 Git 提案](../../../../NoteAgent-docs/docs/03-architecture/ADR/ADR-002-checkpoint与影子Git协同回退.md)
- [TC-REQ-018-001：两阶段验收场景](../../../../NoteAgent-docs/docs/07-quality/TC-REQ-018-001-回退验收场景.md)

技术方案仍为 review：共享材料的冲突与恢复授权范围、版本保留/回收、旧数据切换窗口及恢复失败补偿，尚需评审。历史时间旅行会保留旧分支并重新执行后续节点，不能将图状态分支等同于外部文件和索引已同步恢复。
