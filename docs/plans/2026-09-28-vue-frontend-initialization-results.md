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
| §4.4「Vue 官方入门要求 24.12.0 或以上的 24.x」 | Vue 3 官方快速开始要求 Node 20.19+ / 22.12+；Vite 7.3.6 与 `@vitejs/plugin-vue` 6.0.9 的 `engines` 为 `^20.19.0 \|\| >=22.12.0` | 计划给出的理由不成立。经确认使用本机 **node v22.16.0**／npm 10.9.2，并把该约束写进 `frontend/package.json` 的 `engines`。不下载新 Node |
| §5 Task 1「在可运行的旧页面记录截图」 | Postgres 一度为 Stopped | 用户已启动服务（`postgresql-x64-18` Running），旧页面基线截图按 §2.2 用真实数据取得 |
| §6 `playwright install chromium` | 本机无 Playwright 浏览器缓存，但已安装 Edge | 经确认改用 `channel: 'msedge'`，零下载跑通全部交互测试；`playwright.config.ts` 里留下改用 Chromium 的说明 |
| §4.1 列出的 `tsconfig` 三件套 | 无差异 | 按计划落地 `tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`；未引入 `@vue/tsconfig`，编译选项显式写在文件里 |

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

**后续补充：** 用户随后启动了 Postgres，旧页面已用真实数据实际打开并逐页确认（见 §3 Task 2 的「旧版基线复核」）。

---

### Task 2：建立可构建的 Vue 外壳及页面路由 —— 完成

**新增：** `frontend/` 全部工程文件（`package.json`／`package-lock.json`／`index.html`／
`vite.config.ts`／`tsconfig{,.app,.node}.json`／`vitest.config.ts`／`playwright.config.ts`／
`src/{main.ts,App.vue,router.ts}`／`src/styles/{tokens,base}.css`／`src/layouts/AppShell.vue`／
`src/shared/navigation.ts`／`src/pages/*Page.vue` ×5／`tests/unit/navigation.spec.ts`／
`tests/e2e/navigation.spec.ts`）、`src/noteagent/web/router.py`、`tests/integration/test_frontend_routes.py`。
**修改：** `src/noteagent/web/__init__.py`、`src/noteagent/bootstrap/app.py`、
`src/noteagent/bootstrap/settings.py`、`src/noteagent/chat/router.py`（移出两个 HTML handler）、`.gitignore`。

**锁定的实际版本**（`frontend/package-lock.json` 为准）：node v22.16.0 / npm 10.9.2；
vue 3.5.43、vue-router 4.6.4、pinia 3.0.4、marked 15.0.12、vite 7.3.6、
@vitejs/plugin-vue 6.0.9、typescript 5.9.3、vue-tsc 3.1.x、vitest 3.2.7、@playwright/test 1.63.0。

- [x] 创建 Vue＋TS＋Router＋Pinia＋Vitest＋Playwright 工程，保留项目原 Python 配置。
      npm scripts：`dev`、`build`（先 `vue-tsc -b` 再 `vite build`）、`type-check`、`test:unit`、`test:e2e`。
- [x] 顶部导航与页面路由；页面先放容器，未复制演示内容（Assistant／Library／Settings 明确标注后续任务迁入，
      Records 是空状态）。
- [x] history fallback、`/ui-assets`、vue/legacy 两种模式、`/documents` 兼容路径。
      集成测试用临时 index.html，不要求 Node。
- [x] 导航测试已编写并运行通过。

**命令与真实输出**

```text
$ npm --prefix frontend run type-check
> vue-tsc -b --force          （无输出，退出码 0）

$ npm --prefix frontend run test:unit
 Test Files  1 passed (1)
      Tests  3 passed (3)

$ npm --prefix frontend run build
../src/noteagent/web/dist/index.html                  0.42 kB │ gzip:  0.28 kB
../src/noteagent/web/dist/assets/index-BEbfafUf.css   3.14 kB │ gzip:  1.17 kB
../src/noteagent/web/dist/assets/index-DcYGFYzK.js   92.17 kB │ gzip: 35.92 kB
✓ built in 501ms

$ npm --prefix frontend run test:e2e
  6 passed (7.3s)

$ .venv/Scripts/python.exe -m pytest tests -q
501 passed, 1 warning in 19.15s     （基线 490，本次新增 11，无回归）
```

**真实运行验证（不是截图代替）**

| 验证项 | 方式 | 结果 |
|---|---|---|
| vue 模式六个页面直达 | `FRONTEND_MODE=vue python main.py` 后逐个 curl | `/`、`/assistant`、`/records`、`/library`、`/settings`、`/documents` 全部 200 |
| 产物托管 | 取 `/` 返回里的资源地址再请求 | `/ui-assets/assets/index-*.js` 200、`*.css` 200 |
| 未知资源不被 HTML 吞掉 | curl | `/ui-assets/assets/nope.js` 404、`/api/nope` 404 |
| Vue 应用真的渲染 | 真实 FastAPI 托管的 `/assistant` 上取无障碍快照 | `navigation "主导航"` 下 5 个 link 顺序为 Home／Assistant／Records／Library／Settings，`main` 内出现 Assistant 标题 |
| legacy 回退 | `FRONTEND_MODE=legacy` 重启后 curl | `/` 与 `/documents` 200 且返回旧模板（`citePaneByConv` 命中 17 次）；`/assistant`→`/`、`/records`→`/`、`/settings`→`/`、`/library`→`/documents` 均 307 |

**旧版基线复核（真实数据）**：Postgres 启动后打开旧页面确认了 F01（会话列表 5 条）、
F04（点引用 ② 打开 `Deep_Agents_Context...md` 并把匹配片段选中高亮）、F10–F13（目录树、
已索引／未索引芯片）、F14（聊天模型弹层显示「环境默认（deepseek-v4-flash）」与已启用状态）、
F09（打开右栏后中间区被压缩，与 `chatLayoutBounds` 的收边规则一致）。
草稿面板（F06／F07）因现有会话没有待审草稿，未在旧版复核时取到，留待 Task 4 的 fixtures 用例覆盖。

**完成条件评估：** 原页面可回退（legacy 实测）；新工程能构建、五个路由实际可用；
尚未迁入的业务在页面上与结果文档里都标注为未完成。**F01–F16 没有任何一项在本次提交中被标为已迁移。**

---

### Task 3：建立 API、SSE 与共享模型状态 —— 完成

**新增：** `src/shared/api/{types.ts,http.ts}`、`src/features/chat/{api.ts,sse.ts}`、
`src/features/notes/api.ts`、`src/features/models/{api.ts,store.ts}`、
`tests/fixtures/api.ts`、`tests/unit/{api.spec.ts,sse.spec.ts,model-state.spec.ts}`。
**修改：** `frontend/tsconfig.app.json`（把 `tests/fixtures`、`tests/e2e` 纳入类型检查）。

- [x] 逐项建立 TS 合同。类型与 pydantic schema 字段名一一对应，不做重命名；`/notes/move` 与
      `/notes/folders/rename` 的 JSON 键是 `from`/`to`，`DeleteChatProfile` 的 `expected_revision` 走查询参数——
      三处最容易写错的地方都有单测钉住。
- [x] API 层负责 JSON、204、网络错误与 `message`→`detail`→`error`→`HTTP n` 的提取；**写请求不自动重试**（有单测）。
- [x] SSE 抽成 `consumeSse(stream, onEvent)`，`onEvent` 收 `{event, data: unknown}`；
      另加 `decodeChatEvent` 做协议校验、`TurnAccumulator` 存一轮状态。协议判断不再散落在组件里。
- [x] fixtures 覆盖 conversation／多个 token／sources／answer／draft／工具事件；
      模拟 UTF-8 逐字节分片、空行分片、事件跨块、断流与末行无换行；验证 `answer` 整体替换 token 缓冲、
      `sources` 先后到达都不丢引用。
- [x] models store 复用原状态转换与轮询条件：`revision`／`active` 限制、`unchanged`、
      202 立即进入维护窗口、`visibilitychange` 与 `focus` 由 `init()` 统一注册、`dispose()` 统一清理。
- [x] Vite 开发代理已配置并**实际验证**（见下）。`changeOrigin: false`，不重写 Origin/Host。

**命令与真实输出**

```text
$ npm --prefix frontend run test:unit
 Test Files  4 passed (4)
      Tests  59 passed (59)      （sse 19 / api 19 / model-state 18 / navigation 3）

$ npm --prefix frontend run type-check
> vue-tsc -b --force            （无输出，退出码 0）
```

**开发代理的同源验证**（真实 FastAPI + 真实 Vite 代理，`127.0.0.1:5173 → 127.0.0.1:8000`）

| 请求 | Origin / Host | 结果 | 判读 |
|---|---|---|---|
| `PUT /chat/draft`（真实会话 id） | 均为 `127.0.0.1:5173` | **409** | 过了同源检查并进入业务逻辑（该会话没有待审草稿），配对正确 |
| 同上 | `Origin: https://evil.example` | **403** | 经代理的外部 Origin 仍被拒 |
| `DELETE /model-settings/chat/profiles/does-not-exist` | 均为 `127.0.0.1:5173` | **409** | 模型写请求同样过了同源检查（不存在的配置，零副作用） |
| 同上 | `Origin: https://evil.example` | **403** | 外部 Origin 被拒 |
| `GET /model-settings`、`/notes`、`/conversations` | — | 200 | 读接口代理正常 |
| `GET /assistant`、`/library`、`/documents` | — | 200 | 页面路由不被代理吞掉，SPA 回退正常 |

`require_same_origin` 比较的是 Origin 的 netloc 与 Host，所以上表的「配对正确」不是推断：
同一组请求换掉 Origin 就从 409 变 403。后端既有的跨源拒绝测试也仍然通过（见下方整体回归）。

**完成条件评估：** HTTP／SSE 与维护状态已可独立验证；API 地址、字段与业务动作与旧实现一致。
**本任务仍不迁移任何 UI，F01–F16 的「证据」列保持待迁移。**

---

### Task 4：迁移 Assistant 全部行为 —— 完成

**新增：** `features/chat/{citations.ts,trace.ts,layout.ts,store.ts,ConversationList.vue,MessageList.vue,
ToolTrace.vue,ChatComposer.vue,NotePane.vue,DraftActions.vue}`、
`features/models/{ChatProfiles.vue,ChatProfileForm.vue,EmbeddingSettings.vue,ModelQuickControls.vue}`、
`shared/ui/{confirm.ts,ConfirmDialog.vue,toast.ts,SaveToast.vue,markdown.ts,MarkdownPreview.vue,ResizablePane.vue}`、
`shared/unsaved-guard.ts`、`tests/unit/{citations,layout,chat-state}.spec.ts`、
`tests/e2e/{assistant,drafts-citations}.spec.ts`。
**修改：** `App.vue`、`main.ts`、`layouts/AppShell.vue`、`pages/AssistantPage.vue`、`styles/base.css`。

模型设置组件（`ChatProfiles` / `ChatProfileForm` / `EmbeddingSettings`）在本次就做成可复用组件，
**Task 6 只把它们挂进 Settings 页**，不重写第二份，避免"设置页与快捷弹层两份逻辑"。

**命令与真实输出**

```text
$ npm --prefix frontend run test:unit
 Test Files  7 passed (7)
      Tests  114 passed (114)     （新增 citations 16 / layout 20 / chat-state 19）

$ npm --prefix frontend run test:e2e
  21 passed                      （navigation 6 + assistant 7 + drafts-citations 8）

$ npm --prefix frontend run type-check     （无输出，退出码 0）
$ npm --prefix frontend run build          → dist/index.html + assets（195.6 kB js / 21.5 kB css）
```

**F01–F09、F16（Assistant 部分）的证据**

| 编号 | 证据 |
|---|---|
| F01 | 单测：双击发送只发一次请求、只有一条用户消息；e2e：真实后端下侧栏列出 5 条会话，菜单可重命名（PATCH）与删除（DELETE 后列表少一条） |
| F02 | 单测：`send` 在第一次 await 前上锁；e2e：Shift+Enter 只换行、Enter 才发送、发送后输入框清空；维护窗口下内容退回输入框且不发 `/chat` |
| F03 | 单测：thinking→tool→生成的阶段不会同时挂着两个进行中步骤；e2e：轨迹标题为 `Explored …`，点开后能看到 `Searched …` |
| F04 | 单测：编号重排、未知编号丢弃、`locateQuote` 四级匹配与找不到时返回 -1；e2e：真实后端下点引用打开 `Deep_Agents_Context_Engineering.md` 并精确选中 `## 上下文的类型 …` 片段 |
| F05 | 单测：`saveCitation` 只调 `PUT /notes/Go.md` 并清掉未保存标记；e2e：保存后出现"文件已保存"且请求方法是 PUT |
| F06 | 单测：保存草稿只调 `PUT /chat/draft` 且不碰 `/notes/`；同意前先用同一份正文落库再 review；保存失败则不审批；e2e：8 条草稿用例 |
| F07 | e2e：常驻同意／拒绝，菜单默认不占位，选中后才渲染对应表单；Esc 先收菜单不关面板；replace 没有覆盖入口 |
| F08 | 单测：两个会话各有独立快照、切回来仍是自己的正文、服务端草稿不覆盖本地未保存编辑、慢请求不覆盖新选中会话；e2e：未保存时离开会先问，取消则 URL 与正文都不变 |
| F09 | 单测 20 条覆盖边界与键盘步进、存储值校验与键名；真实后端下两条分隔线渲染为 `role="separator"`，`aria-valuemin/max/now` 随实际宽度走 |
| F16 | 单测：`canSend` 随 busy、`modelActionsLocked` 随流式与重建；e2e：维护窗口下聊天区提示 + 工具栏常驻提示，发送按钮不可用 |

**过程中发现并修掉的两个真实缺陷**（都是测试先失败才暴露的，不是事后补测）：

1. **进行中的那一轮被重复追加。** 写进 `liveTurn` 后组件读到的是 Vue 代理，而 `send` 继续改原始对象：
   既不触发刷新，`liveTurn.value === turn` 也永远为假，收尾时这一轮被同时留在 `liveTurn` 与 `messages` 里。
   改为 `reactive()` 持有代理。这条同时解释了"流式增量不刷新"。
2. **服务端待审草稿不显示。** 快照的默认值 `hidden: true` 让 `applyServerDraft` 永远保持隐藏，
   而旧实现的语义是"只有用户主动收起过才隐藏"。修正为 `existing ? existing.hidden : false`。

另外把首屏"自动打开最近一条会话"改成先比对 `selectionVersion`：用户在列表返回前点了「新对话」时不再抢他的选择。

**完成条件评估：** F01–F09 与 F16 的 Assistant 部分均有单测或 e2e 证据。
流式增量渲染只在单测层验证（e2e 的 `route.fulfill` 不能分段下发），未用真实 provider 跑一轮——
那会消耗用户额度，见 §4.1。

---

### Task 5：迁移 Library 与跨页面保存一致性 —— 完成

**新增：** `features/notes/{store.ts,NoteTree.vue,NoteEditor.vue,IndexChip.vue}`、
`tests/e2e/library.spec.ts`。
**修改：** `pages/LibraryPage.vue`、`features/chat/store.ts`（跨页面刷新）、`shared/unsaved-guard.ts`（Library 分支）。

**命令与真实输出**

```text
$ npm --prefix frontend run test:e2e
  32 passed        （navigation 6 + assistant 7 + drafts-citations 8 + library 11）
$ npm --prefix frontend run test:unit    114 passed
$ npm --prefix frontend run type-check   无输出，退出码 0
$ npm --prefix frontend run build        → 209.9 kB js / 26.0 kB css
```

**F10–F13 的证据**

| 编号 | 证据 |
|---|---|
| F10 | e2e：目录树显示一级目录与根笔记；展开折叠；新建目录后选中它再新建笔记，请求体是 `{file_name: 'bak/新的.md'}`（目录前缀正确） |
| F11 | e2e：打开笔记后编辑区与预览同时更新，未保存圆点出现；保存发 `PUT /notes/Go.md` 且圆点消失；Ctrl+S 保存；离开 Library 会先问，取消则 URL 与正文都不变 |
| F12 | e2e：重命名走 `/notes/move` 且请求体是 `{from: 'Go.md', to: 'Golang'}`（**不是** `from_path/to_path`，也不替用户补 `.md`，与旧页面一致）；删除先确认，取消不发 DELETE；**拖动笔记到目录上**会高亮落点、弹确认、再发 `{from: 'Draft.md', to: 'bak/Draft.md'}` |
| F13 | e2e：已索引／未索引芯片数量正确，点未索引的那个会发 `POST /notes/Draft.md/index` |

**真实后端人工验证：** `/library` 下目录树 24 行、23 个索引芯片；打开
`Deep_Agents_Context_Engineering.md`（12633 字符）后编辑区与预览并排显示，标题栏含索引芯片与修改时间。

**过程中发现并修掉的一个真实缺陷：** 拖拽落点判定读的是 `dataset.folder`，而模板上的属性是
`data-folder-group`（对应的键是 `folderGroup`），所以**任何拖到目录上的操作都会被判成落回根目录**，
根目录下的笔记拖拽直接变成空操作。改为 `dataset.folderGroup` 后拖拽才真正生效。

**跨页面一致性：** 引用面板保存正式笔记后调用 `notes.syncAfterExternalWrite`——目录与索引状态刷新，
Library 打开着同一篇且没有未保存编辑时换上新正文，有未保存编辑则保留并显示"已在别处更新，请核对"。
草稿批准写盘后调用 `refreshAfterExternalChange` 刷新目录。

**完成条件评估：** F10–F13 均有 e2e 证据；`/documents` 打开的就是 Library（有专门用例）；
目录树仍是"树 + 编辑／预览"，没有改成卡片式资料库。

---

### Task 6：迁移 Settings 并复用快捷操作 —— 完成

**新增：** `tests/e2e/settings.spec.ts`。
**修改：** `pages/SettingsPage.vue`、`features/models/ModelQuickControls.vue`（触发按钮补 `aria-label`）。

Task 4 已经把 `ChatProfiles` / `ChatProfileForm` / `EmbeddingSettings` 做成可复用组件并共用同一个
`models` store，所以本任务只把它们挂进设置页，**没有第二份逻辑**，也自动满足"两个入口不各自轮询"：
`models.init()` 只在应用根部调用一次。

**命令与真实输出**

```text
$ npm --prefix frontend run test:e2e
  41 passed      （navigation 6 + assistant 7 + drafts-citations 8 + library 11 + settings 9）
$ npm --prefix frontend run test:unit    114 passed
$ npm --prefix frontend run type-check   无输出，退出码 0
$ npm --prefix frontend run build        → 211.3 kB js / 26.6 kB css
```

**F14–F16 的证据**

| 编号 | 证据 |
|---|---|
| F14 | e2e：普通保存走 `POST /chat/profiles` 且请求体带 `expected_revision: 7`、提示"（未启用）"；保存并启用走 `/chat/activate` 且**不**发 profiles；409 时保留表单内容并显示后端文案；当前启用的配置在表单里只有"保存并启用"、列表里没有"删除"；编辑时 Key 输入框为空且 placeholder 是"留空保留已保存的 Key"；连接测试显示"流式输出正常；工具调用正常" |
| F15 | e2e：候选列表显示可用性与原因（"本地缓存不完整"）；点"重建并切换"发 `{model_id, expected_revision}`，随后显示"正在切换到 …：建立索引（3/10）"并进入维护中；`unchanged` 与失败分支由单测覆盖 |
| F16 | 单测：`canSend` 随 busy、`modelActionsLocked` 随流式与重建；e2e：维护窗口下聊天发送被拒且内容退回输入框、审批按钮禁用；Settings↔Assistant 切换后看到同一批配置（同一份 store） |

**真实后端人工验证：** `/settings` 下显示"环境默认（deepseek-v4-flash）· 已启用 · 凭据来自环境"，
向量候选三个（all-MiniLM-L6-v2 / bge-small-zh-v1.5 / multilingual-e5-small），
当前生效项标"已启用"，索引状态为"已索引 238 个片段 / 19 篇笔记"。

**完成条件评估：** F14–F16 均有 e2e 或单测证据；模型操作没有因为入口从 Chat 改成 Settings＋快捷弹层而丢失。

---

### Task 7：填充最小 Home、Records 空状态与统一美化 —— 完成

**修改：** `pages/HomePage.vue`、`pages/RecordsPage.vue`、`pages/SettingsPage.vue`（卡片样式并到 `.card`）、
`styles/base.css`（新增 `.card`）、`tests/e2e/navigation.spec.ts`。

**命令与真实输出**

```text
$ npm --prefix frontend run test:e2e
  46 passed      （navigation 12 + assistant 7 + drafts-citations 8 + library 11 + settings 8… settings 9）
$ npm --prefix frontend run type-check   无输出，退出码 0
$ npm --prefix frontend run build        → 214.0 kB js / 28.7 kB css
```

- [x] Home 只呈现真实笔记／索引概览与四个导航入口，不新建统计接口：
      数字取自 `GET /notes` 的 `files`（总数 / `indexed=true` / 差值），直接调接口而不是复用 notes store，
      以便区分"读失败"和"读到 0"。
- [x] 分别处理加载、读失败、索引不可用与维护中：读失败显示错误 + 重试且**不显示数字区**；
      索引不可用时显示后端给的原因（"索引 collection 不存在，需要重建。"），不当成逐篇未索引。
- [x] Records 只有空状态说明与两个虚线占位块，没有按钮、没有未来流程；不预留虚假入口。
- [x] 统一间距、字体、边框与按钮：Home 与 Settings 共用同一套 `.card`，焦点态统一走 `:focus-visible`。
- [x] 1440 与 1024 宽度下核对导航、目录树、工具栏与编辑区都可达（有专门用例）。

**真实后端人工验证：** `/` 显示 22 篇笔记 / 17 已索引 / 5 未索引，四个快捷入口（Records 标注"尚未开放"）；
`/records` 只有空状态。

**完成条件评估：** 五页可用或明确空状态；没有模拟业务数据；美化未改动 F01–F16 的行为
（前四个任务的 e2e 全量重跑通过，见下方总数）。

---

## 4. 汇总（随任务推进更新）

| 任务 | 状态 | 提交 | 通过的功能编号 | 验证命令与结果 |
|---|---|---|---|---|
| Task 1 基线与回归清单 | 完成 | `4ada6e0` | — | `pytest tests -q` → 490 passed |
| Task 2 Vue 外壳与路由 | 完成 | `6174f47` | —（外壳） | `type-check`；`test:unit` 3；`test:e2e` 6；`build`；`pytest` 501 |
| Task 3 API／SSE／模型状态 | 完成 | `db954d9` | —（基础设施） | `test:unit` 59；`type-check`；开发代理同源验证 |
| Task 4 Assistant 迁移 | 完成 | `66b777f` | F01–F09、F16（Assistant 部分） | `test:unit` 114；`test:e2e` 21；`type-check`；`build`；真实后端人工验证 |
| Task 5 Library 迁移 | 完成 | `22b47d1` | F10–F13 | `test:e2e` 32；`test:unit` 114；`type-check`；`build`；真实后端人工验证 |
| Task 6 Settings 迁移 | 完成 | `a15f39d` | F14–F16 | `test:e2e` 41；`test:unit` 114；`type-check`；`build`；真实后端人工验证 |
| Task 7 Home／Records／美化 | 完成 | 待填 | —（Home／Records 无 F 项） | `test:e2e` 46；`type-check`；`build`；真实后端人工验证 |
| Task 8 部署接入与总回归 | 未开始 | — | — | — |

### 4.1 未运行项（不得勾选）

- `npm --prefix frontend ci`：本轮用 `npm install` 生成 lockfile，未在干净目录验证 `ci`。
- `docker compose build app`：Dockerfile 尚未加 Node 阶段（Task 8），本轮未验证。
- 真实聊天往返（`POST /chat` 的 provider 调用）：会消耗用户额度，本轮未发起。
- 流式增量的 e2e：`route.fulfill` 一次性下发整个 body，无法断言"token 逐个出现"。
- 真实数据上的写操作（保存笔记、移动、删除、补建索引、改模型配置、切换向量模型）：
  会改用户数据/额度，未在真实后端执行；这些路径由 e2e + 后端测试覆盖。
