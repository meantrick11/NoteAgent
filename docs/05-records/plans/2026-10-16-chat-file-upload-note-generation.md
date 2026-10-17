# 聊天文件上传与笔记生成执行计划

> 执行者：按 Task 0～6 顺序实施；每项先写失败测试，再实现并验证。目标设计见同级 `NoteAgent-docs/docs/03-architecture/ARC-007-聊天文件上传与笔记生成.md`。本文件只记录实施计划，实际结果写入同目录 `2026-10-16-chat-file-upload-note-generation-results.md`。

**目标：** 用户在聊天框上传并解析文件，按消息意图问答或生成待审笔记；原文件独立保存，只有审批后的正式 Markdown 笔记进入 Chroma。

**现有结构：** `HttpApi` 负责 HTTP，`BusinessModules` 负责业务，`TechnicalSupport` 负责磁盘与数据库基础设施，`AppBootstrap` 负责装配；Vue 功能在 `frontend/src/features`。Python 包和文件用 PascalCase，测试用 `Test*.py`。不要使用未纳入主链路的 `src/NoteAgent/modules`。

## 全局规则

- 执行前分别记录 NoteAgent 和 NoteAgent-docs 的 `git status --short`；保留现有用户改动，不重置、不覆盖、不提交无关文件。
- 原件存 `uploads/`，不放 `notes/`，不直接索引。UUID 是稳定身份；显示名与一层逻辑文件夹可变。每次上传生成独立文件记录与 ID；SHA-256 用于完整性核对，不作为唯一约束。
- 首版格式：PDF、DOCX、TXT、MD、PNG、JPEG；20 MB/文件、5 件/消息、PDF 100 页、图片 1600 万像素、单文件解析文本 20 万字符。超限明确失败，不静默截断。
- 持久状态：`queued → parsing → ready/failed → deleted`。浏览器 `uploading` 不持久化。完整解析且结果非空才可 `ready`。图片和无文本 PDF 页走用户标为 `vision` 的模型；专用 OCR 留到后续。
- checkpoint 的用户消息保存附件 ID、名称、解析版本，原件与解析片段留在文件库。同一会话后续可读；跨会话需重新选择；删除后历史引用显示“已不可用”。
- 任何失败都不得伪造已读正文或写入正式笔记；上传文件本身不触发 Chroma。日志不写文件正文、图像或密钥。

## Task 0：上层文档与追溯

**文件：** NoteAgent-docs 新建 `docs/03-architecture/ARC-007-聊天文件上传与笔记生成.md`、`docs/09-decisions/CR-2026-005-聊天文件上传与笔记生成.md`；增补 REQ-013/014、MOD-009、API-005、DATA-002、TC-001、OPS-001/003、GOV-002/003 及必要导航。

- [ ] 在 ARC-007 按业务背景、业务目的、场景、需求拆解、技术实现、业务流程、状态图、上传与草稿时序图、编码和自测计划组织内容；标明目标方案/未实现。
- [ ] REQ-013/014 只追加本期范围，保留 HTML、完整 OCR、坐标和置信度等原有远期条款；原正文不删。现有文件仅更新必要版本、日期、链接和变更记录。
- [ ] 检查图与文字、链接和追溯矩阵；`git diff --check`，人工确认两仓库差异没有无关改动。

## Task 1：模型能力标签

**文件：** `BusinessModules/ModelSettings/ModelContracts.py`、`ModelProfiles.py`、`ModelSettingsStorage.py`，模型设置 API，`frontend/src/features/models/ChatProfileForm.vue` 与共享类型，相关单元/集成测试。

**接口：** `ChatProfile.capabilities: list[Literal["text", "vision"]]`；聊天配置必须有 `text`，`vision` 可选。配置 schema 升级，旧文件自动按 `text` 读取，凭据不变。标签为用户声明，不发送能力探测请求。

- [ ] 先测旧配置读取、保存与回显、缺 `text` 拒绝、无 `vision` 禁止图片解析、模型实际不支持时返回解析失败；运行确认红灯。
- [ ] 实现配置迁移、模型标签和设置 UI；运行针对性测试与模型切换回归，确认绿灯。

## Task 2：来源文件库存储

**新模块：** `BusinessModules/SourceFiles/{SourceFileModels,SourceFileContracts,SourceFileRepository,SourceFileService}.py`、`TechnicalSupport/SourceFileStorage/LocalSourceFileStore.py`、`HttpApi/SourceFileApi/{SourceFileSchemas,SourceFileRoutes}.py`；新 PascalCase Alembic 迁移。

**数据：** SourceFile 保存 `id/display_name/folder/media_type/size_bytes/sha256/status/parse_profile_id/parse_profile_revision/error/created_at/updated_at`；SourceFragment 保存 `source_file_id/ordinal/locator/text`。磁盘以 UUID 命名，用户文件名不能进入物理路径。

- [ ] 先测后缀、multipart MIME、文件头或文本内容校验、大小、空内容、相同 SHA 独立记录、路径穿越、一层文件夹、移动/重命名 ID 稳定、删除墓碑和上传失败清理；确认红灯。
- [ ] 实现服务和 HTTP：单文件 `POST /source-files`，列表/详情/预览/下载、重命名/移动、删除、重试与文件夹管理。写入时使用同源检查和受限路径。
- [ ] 在 AppSettings/ContainerAssembly/AppLifespan/ModelRegistry 装配；补 `.gitignore` 与 Docker 持久卷。跑单元和 API 集成测试，验证重启仍可管理。

## Task 3：格式解析与持久 worker

**新文件：** `BusinessModules/SourceFiles/{TextFileParser,PdfFileParser,DocxFileParser,ImageFileParser,SourceFileWorker}.py`，相关单元/集成测试。

**解析契约：** 各解析器返回有序片段和页码/段落 locator；完整成功才原子发布 `ready` 片段。文本文件本地解码；PDF 文本页本地抽取，无文本页转图给视觉模型；DOCX 保留段落/表格顺序；图片交视觉模型。解析 worker 从数据库领取任务，重启续领未完成任务；不引入外部队列。

- [ ] 先测五种正常格式、扫描页、加密/损坏 PDF、空正文、无 `vision`、模型错误、资源上限、重启与重试；确认红灯。
- [ ] 实现解析器和 worker。视觉任务固定入队时的 profile ID/revision；执行前版本变化则失败并提示重试，任务表不存密钥。
- [ ] 跑解析与恢复测试，确认失败不会留下可读取的部分片段。

## Task 4：Library 文件视图

**前端：** 新建 `frontend/src/features/source-files/{api,store}.ts` 及文件树/预览组件；修改 `frontend/src/pages/LibraryPage.vue`；相关 Vitest/Playwright 测试。

- [ ] 先测“笔记/文件”视图切换、文件列表、单层文件夹、预览/下载、重命名/移动/删除确认、不可编辑原件；确认红灯。
- [ ] 实现 UI。PDF/图片预览原件，文本和 DOCX 显示解析预览并可下载。切回笔记不丢现有未保存编辑状态。
- [ ] 跑 Library E2E 和前端构建。

## Task 5：聊天附件、Agent 与草稿

**文件：** `ChatApi/ChatSchemas.py`、`ChatRoutes.py`、`ConversationState/{TurnExecution,ConversationRecords}.py`、`ChatAgent/{ChatTools,ChatNodes,NoteSources}.py`、`ConversationState/PendingDrafts.py`、`AppBootstrap/RuntimeAssembler.py` 及相关测试。

**接口：** `POST /chat` 新增 `attachment_ids: list[str]`。服务端在创建会话及 `prepare_turn` 前验证去重、最多 5 件和全部 `ready`。接受消息时把 `{id,name,parse_version}` 放入 checkpoint 用户消息；恢复请求不接受新附件。Agent 只能列出和读取当前分支用户消息实际附加的文件，单次片段输出受上下文预算控制。`NoteDraft.source_file_ids` 仅接受已读取且实际使用的文件。

- [ ] 先测未授权/跨会话/未解析/已删除 ID、同会话追问、checkpoint 恢复、历史消息文本编辑保留附件、来源证据、草稿拒绝和审批后索引；确认红灯。
- [ ] 实现聊天接入、受限读取工具、来源栏与提示词。来源栏记录稳定 ID 和名称，不内嵌图片 Markdown 链接。
- [ ] 跑聊天/草稿/恢复集成回归，确认上传、整理、删除原件均不触发 Chroma。

## Task 6：聊天框与整体验收

**前端：** `frontend/src/features/chat/{ChatComposer.vue,api.ts,store.ts}`、消息组件及测试；`frontend/src/features/source-files/` 的上传逻辑。

- [ ] 先测拖放、文件选择、各文件上传/解析状态、上传时编辑文字、失败重试、发送门槛、小 x 语义、Library 选择已有文件和切换会话；确认红灯。
- [ ] 实现上传字节进度及解析状态轮询。上传中小 x 取消请求；上传成功后小 x 只移除本次附件，不删除文件库原件。
- [ ] 运行 `uv run pytest Tests/Unit Tests/Integration -q`、前端 `npm run test:unit`、`npm run build`、相关 Playwright E2E。进行一次真实视觉模型人工验收；缺数据库或模型凭据时如实记录未运行。
- [ ] 新建同目录 `2026-10-16-chat-file-upload-note-generation-results.md`，记录每项命令、通过/失败/未运行、人工样本和风险。证据充分后再更新上层交付状态。

## 完成门槛

用户可以上传和整理文件、看见真实解析状态，在同一会话持续追问，按意图生成可编辑和可审批草稿；文件来源可回看，删除后不被冒充为可读取。原文件始终不进入知识库索引，只有审批后的正式笔记进入索引。

## 2026-10-17 文件记录与上传校验补充

- 正式笔记继续由 `notes/` 和现有审批链路管理；`source_files` 是独立的任意上传文件记录表，与正式笔记不建立数据库外键。
- 文件记录新增 `original_filename`、`storage_path`，保留稳定 UUID、显示名、服务端检测 `media_type`、大小、SHA-256 和时间字段。同内容上传各有独立 ID 与原件，取消 SHA 唯一约束。
- 已知格式核对后缀、请求 MIME 和实际内容；TXT/MD 没有专属文件头，检查 UTF-8 和二进制控制字符。未知格式入库为 `stored` / `application/octet-stream`，只支持下载和整理，不进入聊天解析、草稿来源或索引。
- 上传接口传递 multipart `Content-Type` 给业务校验；响应增加原始文件名、相对存储位置、SHA-256。聊天框对普通入库文件显示不可解析，Library 提供任意文件上传入口。迁移旧记录时用原显示名回填原始文件名、用 UUID 回填相对存储位置。
