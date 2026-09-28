# V2.7 Vue 引入与前端页面初始化执行记录（2026-09-28）

本文件是 [2026-09-28 Vue 引入与前端页面初始化执行计划](./2026-09-28-vue-frontend-initialization.md) 的执行记录。
每个任务完成后回填：改动文件、通过的功能编号、测试命令与真实输出、未做项与偏差。它不是产品状态表——阶段状态仍以
[product/roadmap.md](../product/roadmap.md) 为准。

**证据分级**（全文统一，不得混用）：自动测试通过 / 人工在运行页面验证通过 / 环境阻塞 / 已知旧问题 / 本次新增问题。

---

## 1. Task 1 执行基线

| 项 | 值 |
|---|---|
| 记录时间 | 2026-09-28T14:05+08:00 |
| 新分支 | `feat/vue-frontend-initialization`（从 `feat/draft-in-cite-pane` = `f54e7c8` 创建） |
| 起点提交 | `f54e7c84859307ef41ee3d42548a3521a5edbae5` |
| 相对 main | 领先 6 个提交，落后 0（main 是 HEAD 的祖先，无分叉） |
| 工作区既有改动 | 65 个文件（文档四目录整理：`docs/**`、`evals/**`、各 README）——**原样保留，未回滚、未格式化、未纳入本次提交** |
| 未跟踪（既有） | `docs/guides/`、`docs/plans/2026-09-27-*`、`docs/product/`、`docs/references/亮点的地方.md`、`docs/roadmap/版本1.1代码解析.md`、`evals/criteria/`、`evals/reports/` |
| Python | 3.13.5（`.venv`），`uv` 在本机 shell 下 trampoline 失败，改用 `.venv/Scripts/python.exe -m pytest` |
| Node / npm | node **v22.16.0**、npm **10.9.2** |
| Docker | 未在本轮验证 |

### 1.1 基线测试结果（自动测试）

```
$ .venv/Scripts/python.exe -m pytest tests -q
490 passed, 1 warning in 30.61s
```

1 条 warning 为既有环境噪声（`fastapi.testclient` 提示改用 `httpx2`），与本次改动无关。
**历史计划的 478 passed 不适用于本次基线**，实际为 490。

### 1.2 环境阻塞（影响验证方式，不改变迁移范围）

| 项 | 状态 | 影响 |
|---|---|---|
| Postgres 服务 `postgresql-x64-18` | **Stopped**（`Get-Service` 实测，非单次 TCP 探测） | `python main.py` 在 `alembic upgrade` 处挂起，真实数据联调（`http://127.0.0.1:8000`）本轮不可用 |
| 应用服务器 | 未启动 | 旧页面截图改由「静态托管旧模板 + 隔离 API fixtures」在浏览器中取得，与计划 §6 的 fixtures 方案一致 |
| Node 24.x | 本机只有 22.16.0 | 见 §1.3 |
| Ollama / LM Studio | 不可用（存量事实） | 聊天需远端 provider key |

`python main.py` 会写真实笔记、真实 Chroma 与真实 `var/model_settings`；本轮**不启动**它，也不启动该 Postgres 服务，
以免污染用户数据。需要真实联调时单独确认。

### 1.3 与计划的偏差（已确认项）

| 计划原文 | 实际情况 | 处理 |
|---|---|---|
| §4.4「Vue 官方入门要求 24.12.0 或以上的 24.x」 | Vue 3 官方快速开始要求 Node 20.19+ / 22.12+；`@vitejs/plugin-vue` 与 Vite 7 的 `engines` 为 `^20.19.0 \|\| >=22.12.0` | 本机 node **v22.16.0** 满足已选依赖的 engines，按计划「执行时记录精确版本」执行，不为此下载新版 Node。锁定的实际版本随 Task 2 的 `package.json` 一并记录 |
| §5 Task 1「在可运行的旧页面记录截图」 | Postgres 停止，旧页面无法以真实数据运行 | 改为 fixtures 驱动的浏览器基线（§2.2），并在 Task 8 与 Vue 版做同一 fixtures 的对照截图 |

---

## 2. 迁移基线清单 F01–F16

核查日期 2026-09-28，对照代码：`src/noteagent/web/templates/home.html`（3498 行）、
`src/noteagent/web/static/model-settings.js`（861 行）。行号为基线位置，实现会随迁移变化。

「新入口」列是迁移目标（Vue 组件／模块）；「证据」列在对应任务完成后回填，未回填即视为未验证。

| 编号 | 旧入口（函数／行） | 必须保留的能力 | 新入口 | 证据 |
|---|---|---|---|---|
| F01 | `loadConversations` L2827 / `openConversation` L2867 / `newChat` L2895 / `startRename` L2968 / `openDeleteDialog` L3022 / `confirmDelete` L3035 | 新会话、会话列表、切换、重命名、删除确认、历史恢复；新会话首次发送后拿到服务端 ID | `features/chat/ConversationList.vue` + `features/chat/store.ts` | 待迁移 |
| F02 | `ask` L3069 / `handleKeydown` L2819 / `autoResize` L2814 / `applySendState` L2799 | Enter 发送、Shift+Enter 换行、输入框高度、发送互斥（await 前加锁）、HTTP／流异常反馈、失败后释放发送锁 | `features/chat/ChatComposer.vue` + `store.ts` | 待迁移 |
| F03 | `paintTrace` L3402 / `renderTraceList` L3364 / `finishTrace` L3418 / `ensureGenerating` L3289 / `englishSummary` L3342 | 思考／生成状态、工具过程折叠、实时与历史过程展示；工具内容不混入正式回答 | `features/chat/ToolTrace.vue` + `features/chat/trace.ts` | 待迁移 |
| F04 | `localizeCitations` L1160 / `renderAssistantHtml` L1177 / `locateQuote` L1188 / `openCitedNote` L1963 / `scrollCiteTo` L1956 | 每条消息内编号（1..n 按首现重排）、点击引用、读取笔记、按 quote 匹配选中并滚动；片段失配与文件打不开提示 | `features/chat/citations.ts` + `MessageList.vue` + `NotePane.vue` | 待迁移 |
| F05 | `saveCitedNote` L2010 | 引用面板直接编辑正式笔记并保存；成功后同步已打开的 Library 内容 | `NotePane.vue` + `features/notes/store.ts` | 待迁移 |
| F06 | `applyServerDraft` L1390 / `openDraftPane` L1790 / `saveDraftContent` L1837 / `sendReview` L1885 | 待审草稿恢复、正文编辑、仅保存草稿、同意／拒绝；先保存未保存正文再审批；失败留存可重试 | `NotePane.vue` + `DraftActions.vue` + `features/chat/store.ts` | 待迁移 |
| F07 | `draftOverrideAvailable` L1440 / `renderDraftActions` L1519 / `renderDraftOverrideForm` L1470 / `submitDraftOverride` L1511 / `handleDraftMenuEscape` L1565 | 常驻同意／拒绝、更多菜单、按现有条件（append／create）提供改目标／改动作、Esc 与点击外部关闭 | `DraftActions.vue` | 待迁移 |
| F08 | `snapshotCitePane` L1270 / `restoreCitePane` L1314 / `restoreDraftPane` L1370 / `adoptCitePaneConversation` L1921 / `confirmCiteDiscard` L1939 / `stashDraftForConversation` L1824 | 会话间面板隔离、未保存文本与选区／滚动位置、临时会话（`__pending__`）转正式 ID、关闭／离开确认 | `features/chat/store.ts` + `NotePane.vue` | 待迁移 |
| F09 | `chatLayoutBounds` L1596 / `wirePaneResizeHandle` L1767 / `readStoredChatLayout` L1650 / `keyPaneWidth` L1741 | 会话栏／右侧栏拖拽宽度、键盘调整（方向键／Home／End／Shift 大步）、边界限制、`noteagent.chat-layout.v1` 持久化与窄屏回退 | `shared/ui/ResizablePane.vue` + `features/chat/layout.ts` | 待迁移 |
| F10 | `loadDocuments` L2513 / `renderDocsTree` L2453 / `createNote` L2716 / `createFolder` L2695 | 笔记与一级目录树、展开折叠、新建笔记、新建目录、选中目录下新建 | `features/notes/NoteTree.vue` + `store.ts` | 待迁移 |
| F11 | `openDocument` L2521 / `saveDocument` L2544 / `renderDocsPreview` L2267 / `syncDocsScroll` L2739 | Markdown 编辑与预览、同步滚动、保存提示、Ctrl/Cmd+S、未保存状态和离开保护 | `features/notes/NoteEditor.vue` + `shared/ui/MarkdownPreview.vue` | 待迁移 |
| F12 | `renameNote` L2628 / `renameFolder` L2641 / `deleteFolder` L2671 / `deleteNoteByName` L2570 / `moveNoteTo` L2592 / `onDocsDragEnd` L2398 | 笔记／目录重命名、删除及确认、文件移动、拖拽移动（6px 阈值）与一级目录限制 | `features/notes/NoteTree.vue` + `store.ts` | 待迁移 |
| F13 | `setIndexChip` L2274 / `indexDocument` L2609 / `applyDocsEditingState` L2260 | 已索引／未索引显示、点击未索引项补建、索引处理中与失败反馈、维护期间写操作禁用 | `features/notes/IndexChip.vue` + `store.ts` | 待迁移 |
| F14 | `testConnection` L416 / `submitProfile` L442 / `activateProfile` L519 / `deleteProfile` L490 / `openForm` L353 | 连接测试、新增／编辑／删除配置、保存与保存并启用区分、已启用配置限制（当前配置不能普通保存／删除）、`expected_revision` 冲突处理、Key 不回显与「留空保留」语义 | `features/models/ChatProfiles.vue` + `ChatProfileForm.vue` + `store.ts` | 待迁移 |
| F15 | `loadCandidates` L544 / `switchEmbedding` L555 / `renderJob` L260 / `pollJob` L599 / `refreshIfStale` L122 | 本地向量候选、availability 与 reason、切换／重建修复、`unchanged`、任务状态与进度、成功／失败／中断反馈、页面可见性与跨标签刷新 | `features/models/EmbeddingSettings.vue` + `store.ts` | 待迁移 |
| F16 | `setStreaming` L848 / `canSend` L845 / `onBusyChange` L856；模板 `applyModelBusyState` L2804 | 流式期间模型入口禁用、维护期间聊天发送与笔记写入禁用、已有内容仍可查看 | `features/models/store.ts` + 全局共享状态 | 待迁移 |

### 2.1 已存在链路（不得当成本次新增，也不得重写算法）

- `chat/tools.py` 检索工具把片段存为 `quote`；`chat/citations.py` 登记引用；`chat/router.py` 写进消息。
  前端 `locateQuote` 匹配全文，`setSelectionRange` 选中并 `scrollCiteTo` 滚动。迁移保留该链路与匹配优先级
  （原文 → trim → 压缩空白后取前 32 字符种子）。
- `read_file` 的引用只有文件名、没有 `quote`：点击打开整篇。**保持现状，不在迁移中补段落引用。**
- 重复引文首次匹配、空白匹配回退属于现有行为，记录而不趁机重写。

### 2.2 基线证据方式（替代真实服务器截图）

Postgres 停止使真实页面不可达。基线改用与计划 §6 一致的隔离方式：静态托管 `home.html`，
用 Playwright 拦截 `/conversations`、`/notes`、`/model-settings` 等返回固定 fixtures，
得到可复现的旧版界面快照，Task 8 再用同一组 fixtures 对照 Vue 版。

---

## 3. 逐任务执行记录

### Task 1：固化迁移基线与回归清单 —— 完成

**改动文件：** 新增本文件。未改任何应用代码、测试或依赖。

- [x] 记录当前提交、工作区改动、运行环境；建立 F01–F16 的旧入口／新入口／证据列（§2）。
- [x] 运行 `pytest tests -q`，保存**本次**结果：490 passed（§1.1）。
- [ ] 旧页面截图（Assistant／引用草稿／Documents／模型弹层）——因 Postgres 停止，改为 §2.2 的 fixtures 基线，
      在 Task 2 建立 Playwright 工程后补拍。
- [x] 记录代码与实际页面不一致之处：§2.1 与 §1.3。

**完成条件评估：** 功能基线可按 F01–F16 对照；已有失败（无）与环境限制（Postgres 停止、Node 22.16.0）已明确。
唯一未完成项是截图，已说明替代方案与补拍时机。

---

## 4. 汇总（随任务推进更新）

| 任务 | 状态 | 提交 | 通过的功能编号 | 验证命令与结果 |
|---|---|---|---|---|
| Task 1 基线与回归清单 | 完成 | 待填 | — | `pytest tests -q` → 490 passed |
| Task 2 Vue 外壳与路由 | 未开始 | — | — | — |
| Task 3 API／SSE／模型状态 | 未开始 | — | — | — |
| Task 4 Assistant 迁移 | 未开始 | — | — | — |
| Task 5 Library 迁移 | 未开始 | — | — | — |
| Task 6 Settings 迁移 | 未开始 | — | — | — |
| Task 7 Home／Records／美化 | 未开始 | — | — | — |
| Task 8 部署接入与总回归 | 未开始 | — | — | — |

### 4.1 未运行项（不得勾选）

- `npm ci` / `npm run build` / `npm run test:unit` / `npm run test:e2e`：前端工程尚未建立。
- `docker compose build app`：Docker 路径本轮未验证。
- `python main.py` 真实联调：Postgres 停止，见 §1.2。
