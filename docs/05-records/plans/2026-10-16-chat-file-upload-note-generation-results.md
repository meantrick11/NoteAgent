# 聊天文件上传与笔记生成：执行结果

日期：2026-10-16。对应 [执行计划](2026-10-16-chat-file-upload-note-generation.md)。本文记录当前工作区证据，不代表已经完成生产环境验收。

## 实施范围

| 任务 | 当前结果 | 证据与限制 |
|---|---|---|
| 0 上层文档 | 已写入目标方案 | NoteAgent-docs 新增 ARC-007、CR-2026-005；增补 REQ-013/014、MOD-003/007/008/009、API-002/005、DATA-002、TC-001、OPS-001/003 和追溯导航，均保留 review 状态。链接检查无缺失。 |
| 1 模型能力标签 | 已实现 | `ChatProfile` 保存/回显 `text/vision`，旧配置默认 `text`，保存时升级 schema 2；标签为用户自我声明，连接测试不代表视觉能力验证。 |
| 2 文件库存储 | 已实现核心路径 | 独立 `uploads/`、UUID 原件、PostgreSQL 元数据/解析片段、每次上传独立记录与稳定 ID、删除墓碑。相同字节仍创建新 ID，旧历史引用在删除后不可用。Alembic revision `f8c2d3e5b014` 为 head。 |
| 3 解析 worker | 已实现自动路径 | TXT/MD、DOCX、PDF、PNG/JPEG；PDF 无文本页和图片通过标记 `vision` 的模型。文本 20 万字符、PDF 100 页、图片 1600 万像素，失败不发布 ready。应用内 worker 启动时重领 `parsing`，解析片段原子发布。真实视觉模型尚未人工验收。 |
| 4 HTTP/Library | 已实现并有测试 | 上传、状态、预览、下载、重命名、移动、删除、重试和一层文件夹；Library 笔记/文件视图。文件操作不触发 Chroma。 |
| 5 聊天/checkpoint/Agent | 已接入，数据库端到端待验 | 服务端在新会话创建前验证附件 ready、去重、最多 5 个；恢复请求不能新增附件。checkpoint 用户消息保存 ID/名称/解析版本。Agent 从当前分支消息建立授权集，按需读取并限制单次输出；草稿来源 ID 必须有实际读取证据，仍走原审批链路。需要 PostgreSQL 环境验证真实 checkpoint 恢复。 |
| 6 聊天交互与验收 | 已实现界面，部分验收待环境 | 聊天拖放/选择上传、进度和解析状态、取消/重试、文件库选择、发送门槛及消息附件显示；历史删除状态显示不可用。真实视觉模型和完整 PostgreSQL 流程待人工验收。 |

## 自测命令与结果

| 命令 | 结果 |
|---|---|
| `uv lock`、`uv sync --frozen` | 通过；新增 pypdf、python-docx、Pillow、pypdfium2 并更新 uv.lock。 |
| `.venv/Scripts/python.exe -m pytest Tests/Unit Tests/Integration/TestApp.py Tests/Integration/TestSourceFileApi.py Tests/Integration/TestModelSettingsApi.py -q -k "not test_upper_modules_have_explicit_pascal_case_names and not test_all_python_application_packages_and_files_use_pascal_case"` | 575 passed，2 deselected。两项排除的目录规范测试被执行前已有的未跟踪 `src/NoteAgent/modules/`、`src/NoteAgent/bootstrap/` 触发；这些目录不是本任务代码，未改动。 |
| `npm run test:unit` | 147 passed。 |
| `npm run build` | 通过。 |
| `npm run test:e2e -- tests/e2e/source-files.spec.ts` | 2 passed，覆盖文件视图、聊天上传解析状态及移除。 |
| `npm run test:e2e -- tests/e2e/library.spec.ts` | 11 passed，现有笔记 Library 回归。 |
| `.venv/Scripts/python.exe -m alembic heads` | `f8c2d3e5b014 (head)`。 |
| `git diff --check`（上层文档仓库） | 无本任务空白错误；命令只报告既有文件的 LF/CRLF 提示。 |

`uv run pytest ...` 在本机报 `uv trampoline failed to canonicalize script path`，所以 Python 测试改用当前 `.venv/Scripts/python.exe -m pytest`。完整 `Tests/Integration` 在 `TestCheckpointChatApi` 的 PostgreSQL 用例处停滞；本机 Docker daemon 未运行，无法在本次执行中启动所需数据库。未把这些用例记为通过。

本机虽有 `postgresql-x64-18` 服务，但服务处于停止状态，当前账户执行 `Start-Service` 被系统拒绝；因此没有直接启动或修改用户数据库。

## 后续验收与剩余风险

1. 在有 PostgreSQL 的环境运行 `alembic upgrade head`、完整 `Tests/Integration`，验证新会话附件、同会话追问、编辑历史、进程中断后恢复、删除后读取拒绝，以及审批后才入 Chroma。
2. 用实际标记 `vision` 的模型分别解析 PNG/JPEG 和无文本 PDF；观察配置变更、视觉调用失败时状态为 `failed`，并核对笔记来源与人工审批。
3. 用最大尺寸与损坏样本验证资源上限、解析任务重启、同内容并发上传和删除时并发读取。当前已有单元和 HTTP 集成覆盖常见样本，尚无生产数据库与模型环境证据。
4. 上层文档继续保持 `review/目标方案`；在以上人工验收和完整数据库回归完成前，不标记 REQ-013/014 的远期 HTML、专用 OCR、坐标与置信度目标为已实现。

## 2026-10-17 任意上传与三重校验补充

- 两仓库均在 `codex/upload-file-validation-records` 分支；创建分支前先记录了各自 `git status --short --branch`，没有重置、暂存或提交原有差异。
- 上层 ARC-007、REQ-013、API-005、DATA-002、TC-001、CR-2026-005 已只增补范围修订：上传记录独立于正式笔记；未知格式普通入库；可解析聊天格式保持原范围；同 SHA 不再复用 ID。
- `source_files` 增加 `original_filename` 与 `storage_path`；后续 Alembic 迁移回填旧记录并移除 SHA 唯一索引。原件继续独立存于 `uploads/`；现有数据库未执行迁移。
- 已知格式检查后缀、multipart MIME、文件签名或文本内容；未知格式以 `stored` 和 `application/octet-stream` 保存，不能进入聊天或 AI。未知格式无通用文件头，不能宣称完成文件头校验。
- 定向上传测试：`Tests/Unit/TestUploadedFileRecords.py` 6 通过；`Tests/Integration/TestSourceFileApi.py::test_upload_rejects_mime_conflict_and_exposes_record_fields` 1 通过；迁移测试 `Tests/Integration/TestUploadedFileMigration.py` 1 通过；相关原测试 13 通过。
- 前端 `npm run test:unit`：147 通过；`npm run build`：通过。后端全量 `.venv/Scripts/python.exe -m pytest Tests/Unit Tests/Integration -q --ignore=Tests/Unit/TestSourceOrganization.py`：711 通过、1 跳过、31 个 PostgreSQL fixture 连接超时，属于环境阻断，不记为通过。真实 PostgreSQL 迁移与真实视觉模型人工验收仍待环境验证。

最终定向复测：`.venv/Scripts/python.exe -m pytest Tests/Unit/TestUploadedFileRecords.py Tests/Unit/TestSourceFiles.py Tests/Unit/TestSourceFileTools.py Tests/Integration/TestSourceFileApi.py Tests/Integration/TestUploadedFileMigration.py -q`，21 通过；`npm run test:e2e -- tests/e2e/source-files.spec.ts`，3 通过（Playwright 本地回环地址）。全量测试的 31 个错误均为 PostgreSQL 连接超时，未对现有数据库执行迁移。
复核修复后最终前端验证：`npm run test:e2e -- tests/e2e/source-files.spec.ts` 6 通过，覆盖任意文件入库、批量上传单件失败继续、Enter 发送门槛、轮询故障恢复；`npm run test:unit` 147 通过；`npm run build` 通过。定向后端 21 通过。已明确上传阶段检查文件签名/文本内容，完整可解析性由 worker 判定，只有完整解析后才为 `ready`。
