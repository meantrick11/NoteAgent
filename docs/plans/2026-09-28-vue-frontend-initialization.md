# V2.7 Vue 引入与前端页面初始化执行计划

> **后续变更说明（2026-09-28）：** 本文五个顶部文字导航是首轮迁移基线。其后的“顶部四工作入口＋设置齿轮”和设置分类按 [增量计划](2026-09-28-settings-navigation-and-sections.md) 执行**并已完成**，记录见 [结果文档](2026-09-28-settings-navigation-and-sections-results.md)；保留本文原步骤用于追溯，不重新执行初始化或覆盖已迁移功能。

> **交接对象：Qoder。** 按任务顺序执行、逐项勾选并记录验证结果。本文是待执行计划，不代表功能已实现。本次编写只新增计划，不修改应用。

**目标：** 以现有页面代码为功能基线，引入 Vue，将已有功能完整迁移到五个顶部导航页面；允许视觉美化，不删减能力，不借迁移重新定义业务。

**架构：** 一个 Vue SPA、一个统一顶部导航、五个页面模块，继续使用现有 FastAPI API、PostgreSQL、Markdown 和向量索引。将当前集中在模板中的界面与状态拆为组件及业务模块，不变更 Agent、生成策略、检索策略或草稿存储模型。

**技术方案：** Vue 3、TypeScript、Vite、Vue Router、Pinia；原生 fetch；保留 Markdown 编辑与预览方式，首轮不引入富文本编辑器或大型 UI 组件库。Vitest 与 Playwright 分别覆盖状态逻辑与用户交互。以上为本计划的实施选型，不是当前仓库已安装依赖。

**依据：** [前端产品结构与架构决策](../product/versions/1.5.0/frontend-architecture.md)、[现行前端](../architecture/frontend.md)、[路线图](../product/versions/1.5.0/roadmap.md)，以及 2026-09-28 本次用户约束。发生冲突时，以本次用户约束为准。

## 1. 用户已确定的范围

- V2.2／V2.3 暂按当前可用处理；完成 V2.7 后继续其他 V2 迭代。不把此次优先级调整写成全面验收通过。
- 顶部横栏顺序固定：**Home → Assistant → Records → Library → Settings**。
- Home 是已有数据的概览及其他四页的快捷入口。只展示当前接口可支持的数据；复习内容等尚无能力支撑的项目只预留布局扩展位置。
- Assistant 承接当前 Chat，Library 承接当前 Documents，Settings 承接当前模型与索引管理。
- Records 只初始化页面入口和空状态，不定义视频、会议、网页等未来工作流程。
- 页面可以调整间距、颜色、字体、边框、按钮一致性与响应式布局；已有内容、动作语义和交互能力必须保留。
- 不增加资料侧 AI 对话、整理方案、复习系统、录制、网页抓取、任务中心、统计数据库或独立任务草稿。
- 本次没有决定 Records 最终承载哪些来源；不得把讨论中的候选方案当作已授权功能。
- 不改用户笔记、数据库数据、已有模型配置、Prompt、检索参数与引用生成协议。
- 不因引入 Vue 删除已有测试；依赖旧 DOM 的测试迁移到等价用户行为验证，并记录映射。
- 当前工作区已有大量文档整理改动。执行前记录 `git status --short`，不得回滚、批量格式化或混入这些无关改动。

## 2. 代码基线与现有能力清单

核查日期：2026-09-28。函数名是定位依据，行号可能随实现变化。执行前重新核对最新代码；新出现的既有能力也必须纳入迁移。

| 编号 | 现有代码入口 | 必须保留的能力 | 新归属 |
|---|---|---|---|
| F01 | `web/templates/home.html`：`loadConversations/openConversation/newChat/startRename/confirmDelete` | 新会话、会话列表、切换、重命名、删除确认、历史恢复；新会话第一次发送后获得服务端 ID | Assistant |
| F02 | 同文件：`ask/handleKeydown/autoResize` | Enter 发送、Shift+Enter 换行、输入框高度、发送互斥、HTTP／流异常反馈、失败后释放发送锁 | Assistant |
| F03 | 同文件：`paintTrace/renderTraceList/finishTrace` | 思考／生成状态、工具过程折叠、实时与历史过程展示；工具内容不混入正式回答 | Assistant |
| F04 | 同文件：`localizeCitations/renderAssistantHtml/locateQuote/openCitedNote/scrollCiteTo` | 每条消息内编号、点击引用、读取笔记、按 quote 匹配选中并滚动；片段失配与文件打不开提示 | Assistant |
| F05 | 同文件：`saveCitedNote` | 引用面板直接编辑正式笔记并保存；成功后同步已打开的 Documents 内容 | Assistant／Library 共享数据 |
| F06 | 同文件：`applyServerDraft/openDraftPane/saveDraftContent/sendReview` | 待审草稿恢复、正文编辑、仅保存草稿、同意／拒绝；先保存未保存正文再审批；失败留存可重试 | Assistant |
| F07 | 同文件：`draftOverrideAvailable/renderDraftActions/renderDraftOverrideForm/submitDraftOverride` | 常驻同意／拒绝、更多菜单、按现有条件提供改目标／改动作选项、Esc 与菜单关闭行为 | Assistant |
| F08 | 同文件：`snapshotCitePane/restoreCitePane/adoptCitePaneConversation/confirmCiteDiscard` | 会话间面板隔离、未保存文本与选区／滚动位置、临时会话转正式 ID、关闭／离开确认 | Assistant |
| F09 | 同文件：`chatLayoutBounds/wirePaneResizeHandle/readStoredChatLayout` | 会话栏／右侧栏拖拽宽度、键盘调整、边界限制、持久化与窄屏回退 | Assistant |
| F10 | 同文件：`loadDocuments/renderDocsTree/createNote/createFolder` | 笔记与一级目录树、展开折叠、新建笔记、新建目录、选中目录下新建 | Library |
| F11 | 同文件：`openDocument/saveDocument/renderDocsPreview/syncDocsScroll` | Markdown 编辑与预览、同步滚动、保存提示、Ctrl/Cmd+S、未保存状态和离开保护 | Library |
| F12 | 同文件：`renameNote/renameFolder/deleteFolder/deleteNoteByName/moveNoteTo/onDocsDragEnd` | 笔记／目录重命名、删除及确认、文件移动、拖拽移动与原有目录限制 | Library |
| F13 | 同文件：`setIndexChip/indexDocument/applyDocsEditingState` | 已索引／未索引显示、点击未索引项补建、索引处理中与失败反馈、维护期间写操作禁用 | Library |
| F14 | `web/static/model-settings.js`：`testConnection/submitProfile/activateProfile/deleteProfile` | 连接测试、新增／编辑／删除配置、保存与保存并启用区分、已启用配置限制、revision 冲突处理 | Settings＋Assistant 快捷入口 |
| F15 | 同文件：`loadCandidates/switchEmbedding/renderJob/pollJob/refreshIfStale` | 本地向量候选、不可用原因、切换／重建修复、任务状态、成功／失败反馈、页面可见性与跨标签刷新 | Settings＋Assistant 快捷入口 |
| F16 | 同文件：`setStreaming/canSend/onBusyChange`；模板 `applyModelBusyState` | 流式期间模型操作限制、维护期间聊天与笔记写入限制、已有内容仍可查看 | 全局共享状态 |

### 2.1 已存在的定位，不能重复当成新需求

`chat/tools.py` 的检索工具将片段存为 `quote`；`chat/citations.py` 登记引用，`chat/router.py` 保存到消息；前端 `locateQuote` 匹配全文，`setSelectionRange` 选中并滚动。迁移必须保留该链路。

当前 `read_file` 的引用只有文件名、没有 quote，点击能打开整篇；保持当前语义，不在迁移中补段落引用。重复引文首次匹配、空白匹配回退属于现有行为，记录而不趁机重写算法。

### 2.2 后端与构建现状

- `src/noteagent/chat/router.py` 的 `GET /` 与 `GET /documents` 均调用 `web.read_home_html()` 返回同一模板。
- `src/noteagent/bootstrap/app.py` 挂载 `/static` 并注册 chat、notes、model-settings router。
- `src/noteagent/web/__init__.py` 定义模板／静态目录和模板读取函数。
- 当前无前端 package.json、Vite 工程或真实浏览器测试套件；`tests/e2e/` 当前只有说明文件。
- 当前 Markdown 来自模板里的 CDN marked；迁移为 npm 锁定依赖后，必须验证原有渲染结果。
- Dockerfile 目前只有 Python 构建，没有 Node 阶段；`.dockerignore` 已忽略 dist，需由镜像内构建生成前端产物。

## 3. 页面初始化设计：以旧页面为内容来源

| 路由 | 初始化内容 | 首轮约束 |
|---|---|---|
| `/` | Home：笔记数量、已索引／未索引数量、四个快捷入口 | 数据取现有接口；不增加趋势图、复习统计、活动流、虚构任务或最近内容模块 |
| `/assistant` | 原 Chat 页面主体，增加统一顶部导航 | 保留会话栏、聊天区、按需出现的右侧引用／草稿面板及模型快捷操作 |
| `/records` | 标题和说明当前尚未开放的空状态容器 | 不绘制虚假记录、进度、录制按钮或新业务表单；结构可扩展即可 |
| `/library` | 原 Documents 主体 | 目录树、编辑／预览、管理动作和索引状态均迁移；不擅自换成卡片资料库 |
| `/settings` | 现有聊天配置、向量配置与索引维护内容 | 将同一套设置组件同时用于设置页与 Assistant 快捷弹层，避免功能缩水或两份逻辑 |
| `/documents` | 兼容跳转到 `/library` | 不再承担独立实现；旧 URL 可访问 |

顶部五项固定顺序，当前页有选中态；窄屏保持可访问，可横向滚动，不把入口直接隐藏。Home 快捷入口与顶部链接指向同一路由。

Home 统计取 `GET /notes` 的 `files`：总数为长度，已索引为 `indexed=true` 数量，未索引为差值。配合 `/model-settings` 的 `retrieval_available/retrieval_state/busy` 显示不可用或重建状态；不要把索引不可用时的 false 当作正常可修复的逐篇未索引状态。请求失败显示错误与重试，不能显示为零。暂不显示复习数字，布局用可扩展网格预留能力，无需占满屏幕的空卡片。

首轮视觉改动局限于设计变量、统一控件样式和空间分配；保留现有文案与内容顺序，新增导航／空状态／状态错误文案除外。先完成等价迁移，再集中美化，方便回归归因。

## 4. 工程、状态和接入方案

### 4.1 新建文件与职责

以下路径均相对仓库根目录。文件结构是实施目标，不是现有文件。

```text
frontend/
  package.json / package-lock.json / index.html
  vite.config.ts / tsconfig.json / tsconfig.app.json / tsconfig.node.json
  vitest.config.ts / playwright.config.ts
  src/
    main.ts / App.vue / router.ts
    styles/tokens.css / styles/base.css
    layouts/AppShell.vue
    pages/HomePage.vue / AssistantPage.vue / RecordsPage.vue
    pages/LibraryPage.vue / SettingsPage.vue
    shared/api/http.ts / shared/api/types.ts
    shared/ui/ConfirmDialog.vue / shared/ui/MarkdownPreview.vue
    shared/ui/ResizablePane.vue / shared/ui/SaveToast.vue
    shared/navigation.ts
    features/chat/api.ts / features/chat/store.ts / features/chat/sse.ts
    features/chat/citations.ts / features/chat/trace.ts / features/chat/layout.ts
    features/chat/ConversationList.vue / features/chat/MessageList.vue
    features/chat/ChatComposer.vue / features/chat/ToolTrace.vue
    features/chat/NotePane.vue / features/chat/DraftActions.vue
    features/notes/api.ts / features/notes/store.ts
    features/notes/NoteTree.vue / features/notes/NoteEditor.vue
    features/notes/IndexChip.vue
    features/models/api.ts / features/models/store.ts
    features/models/ChatProfiles.vue / features/models/ChatProfileForm.vue
    features/models/EmbeddingSettings.vue / features/models/ModelQuickControls.vue
  tests/unit/api.spec.ts / tests/unit/sse.spec.ts
  tests/unit/citations.spec.ts / tests/unit/chat-state.spec.ts
  tests/unit/layout.spec.ts / tests/unit/model-state.spec.ts
  tests/e2e/navigation.spec.ts / tests/e2e/assistant.spec.ts
  tests/e2e/drafts-citations.spec.ts / tests/e2e/library.spec.ts
  tests/e2e/settings.spec.ts
  tests/fixtures/api.ts
```

`NotePane` 仍区分 citation／draft 两种模式；复用外壳与输入组件，不合并保存动作。不要将整个旧模板作为 `v-html` 注入或把所有 DOM 操作搬进一个 Vue mounted 回调。

### 4.2 状态归属与迁移约束

- chat store 持有当前会话、消息、发送锁、正在生成的 turn、各会话面板快照；以请求发起时的会话 ID 处理回包，禁止回包时读当前选中的 ID 决定归属。
- 对话发送仍全局最多一个进行中请求，且在第一次 await 之前加锁。首轮不增加多会话并发。
- 原页面切换是隐藏 DOM 而不是停止 fetch。Vue 内切换一级页面不得默认取消正在进行的聊天流；连接由 store 管理，组件只订阅。浏览器刷新／关闭不承诺后台继续生成或断线续传。
- 切换会话沿用现有发送期间限制；异步读取用请求序号或 AbortController 防止慢请求覆盖新选择。
- notes store 持有目录、当前文档、未保存正文、预览同步与索引操作状态。面板快照继续按会话隔离，不擅自引入新的跨文档自动保存策略。
- 同一文件通过引用面板保存后，刷新目录与索引状态；Library 已打开且无未保存编辑时更新正文，有未保存编辑时保留并提示重新核对，不能静默覆盖。
- models store 是模型配置、revision、busy、向量任务及轮询的唯一来源；Settings 和快捷入口共用。visibilitychange／focus 监听由应用统一注册与清理，不能每切页增加一份轮询。
- route guard 覆盖顶部、快捷入口、浏览器前进后退；beforeunload 覆盖刷新关闭。未保存编辑取消离开时，URL、选中页、文本都保持一致。确认放弃只清理当前动作确实放弃的缓冲，不能清其他会话草稿。
- `noteagent.chat-layout.v1` 的宽度记忆与原限制保留；设置密钥不进入 localStorage 或持久化 store。
- 只把现有状态转成可维护结构，不引入离线缓存、全局任务总线、插件注册系统。

### 4.3 保留 API 合同

| 领域 | 现有端点／数据来源 | 必须核对的合同 |
|---|---|---|
| 会话 | `/conversations` 及 `/{id}`、`/{id}/messages` | 列表、详情、PATCH、DELETE；消息含 citations/tool_steps；详情含 pending_draft |
| 聊天 | `POST /chat` | JSON `{question, conversation_id}`；fetch 读取 SSE，不用只支持 GET 的原生 EventSource 替换 |
| 草稿 | `PUT /chat/draft`、`POST /chat/review` | 保存 `{thread_id, content}`；审批 `{thread_id, action, write_action?, file_name?}`；业务失败可能在 JSON 内，不能只判断 HTTP 200 |
| 资料 | `/notes`、`/notes/{file_name:path}`、`/notes/{file_name:path}/index` | 列表、创建、读取、保存、删除、逐篇索引；保持嵌套路径逐段编码 |
| 目录／移动 | `/notes/folders`、`/notes/folders/rename`、`/notes/folders/{name}`、`/notes/move` | 重命名／移动 JSON 是 `from/to`，不可直接发送 TS 内部变量名 |
| 设置 | `/model-settings`、`/chat/test`、`/chat/profiles`、`/chat/profiles/{id}`、`/chat/activate` | 后五项均相对 `/model-settings`；完整类型以 `model_management/schemas.py` 为准，保留 expected_revision 和凭据保留语义 |
| 向量 | `/model-settings/embeddings`、`/model-settings/embedding/switch`、`/model-settings/jobs/{id}` | 同模型修复、unchanged、job 状态、失败与不可用原因 |

SSE 需逐一支持现有 `conversation/thinking/generating/think/tool/tool_done/draft/sources/answer/token` 事件。`answer` 是服务端清理后的完整文本，必须替换而非追加；sources 到达顺序不能造成永久缺失引用；历史引用与实时引用用同一套渲染逻辑。解析器处理 UTF-8 跨块、事件跨块、连续事件、空行、注释心跳及流结束，不能假设一次 reader.read 就是一个完整 JSON。

### 4.4 路由、开发、打包与回退

- Vue Router 用 HTML5 history。页面只占 `/`、`/assistant`、`/records`、`/library`、`/settings`、`/documents`，首轮不额外定义会话／文件深链接。
- 新增 `src/noteagent/web/router.py` 管理页面路由；从 chat/router.py 移走两个 HTML handler，保留全部业务路由。`bootstrap/app.py` 注册 web router。
- 在 `web/__init__.py` 增加前端产物读取，保留 `read_home_html` 供回退使用。Vite 产物放 `src/noteagent/web/dist/`，资源路径固定 `/ui-assets/`，FastAPI 独立静态挂载；旧 `/static` 保留给回退页面。
- 仅为上述明确页面返回 SPA HTML。未知 API、不存在的 JS/CSS 必须返回 404，不能被兜底 HTML 吞掉。
- 开发期 Vite 将 `/chat`、`/conversations`、`/notes`、`/model-settings` 代理到 `http://127.0.0.1:8000`。四者不会与新页面路由冲突。
- `require_same_origin` 实际比较 Origin 的 netloc 与 Host，不检查 Referer。Vite 开发代理设置 `changeOrigin: false`，保留浏览器请求的 Host 与 Origin 配对，不重写任意外部 Origin 来伪装同源；不得关闭服务端同源检查或增加宽泛 CORS。以真实草稿 PUT 和模型 POST 验证开发代理，同时验证外部 Origin 仍被拒绝。
- 本地构建使用 npm，提交 lockfile，安装用 npm ci。Node 使用满足已选依赖 engines 的 24.x 版本（本次 Vue 官方入门要求 24.12.0 或以上的 24.x）；执行时记录精确版本，不凭旧经验指定过低版本。
- Docker 增加 Node 构建阶段，执行 npm ci 和 npm run build，再把产物复制进 Python 最终镜像；运行容器仍只有现有 FastAPI 服务，不增加生产 Vite server 或新端口。
- `.gitignore/.dockerignore` 补充 node_modules、Playwright 报告与本地测试结果；dist 不入库，由构建阶段生成。检查 Python wheel 包含已构建的 web/dist，必要时在 pyproject.toml 增加明确 artifact 配置。
- 增加 `Settings.frontend_mode`，取 `legacy/vue`，初始默认 legacy。迁移过程原 `/` 和 `/documents` 继续可用；开发 Vue 走 Vite。完整验收后默认切 vue，本地先构建，Docker 自动构建。
- vue 模式找不到 index.html 时返回明确 503 构建提示，不影响 API 初始化，不静默显示旧页假装迁移成功。legacy 模式 `/` 与 `/documents` 原样，`/assistant` 跳 `/`，`/library` 跳 `/documents`，另外三页回 `/`；记录这是回退模式。
- 回退通过 `FRONTEND_MODE=legacy` 重启应用，不修改数据。首轮交付保留旧模板／静态脚本；删除旧实现另开清理任务。

## 5. 分任务执行

### Task 1：固化迁移基线与回归清单

**文件：** 读取第 2 节对应代码、`tests/integration/test_app.py`、`tests/integration/test_model_settings_api.py`、`tests/unit/test_chat_tools.py`；新建 `docs/plans/2026-09-28-vue-frontend-initialization-results.md`。

- [ ] 记录当前提交、工作区改动、运行环境；在结果文档逐项建立 F01–F16 的旧入口／新入口／验证证据列。
- [ ] 运行 `uv run pytest tests -q`，保存实际结果；历史 478 passed 不可复制成此次结果。
- [ ] 在可运行的旧页面记录 Assistant、引用／草稿、Documents、模型弹层截图及关键动作；使用测试笔记，不修改私人正式笔记来做验收。
- [ ] 记录代码与实际页面不一致的地方；已存在的问题单列，不在迁移里隐式改变业务。

**完成条件：** 功能基线可以供迁移前后对照，已有失败与环境限制明确。

### Task 2：建立可构建的 Vue 外壳及页面路由

**新增：** frontend 工程配置、main.ts、App.vue、router.ts、AppShell.vue、五个 page、tokens.css/base.css、navigation.spec.ts、`tests/integration/test_frontend_routes.py`。
**修改：** web/__init__.py、新增 web/router.py、bootstrap/app.py、bootstrap/settings.py、chat/router.py、.gitignore。

- [ ] 创建 Vue＋TS＋Router＋Pinia＋Vitest＋Playwright 工程，保留项目原 Python 配置。定义 npm scripts：`dev`、`build`（先 vue-tsc 再 vite build）、`type-check`、`test:unit`（vitest run）、`test:e2e`（playwright test）。
- [ ] 实现顶部导航与明确页面路由，页面先放容器，不复制演示内容；设置页／业务页真实内容在后续任务迁入。
- [ ] 落实 history fallback、`/ui-assets`、vue/legacy 模式以及 `/documents` 兼容路径。测试用临时 index.html 和静态文件，不要求 Python 单元测试先安装 Node。
- [ ] 编写下面的导航测试并运行，确认新应用能浏览五页、刷新不丢路由；不存在的 API／资源不返回 HTML。

```ts
import { test, expect } from '@playwright/test'

test('顶部入口顺序固定且各页面可刷新', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.getByRole('link')).toHaveText([
    'Home', 'Assistant', 'Records', 'Library', 'Settings',
  ])
  for (const [label, path] of [
    ['Assistant', '/assistant'], ['Records', '/records'],
    ['Library', '/library'], ['Settings', '/settings'], ['Home', '/'],
  ]) {
    await nav.getByRole('link', { name: label, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await page.reload()
    await expect(nav.getByRole('link', { name: label, exact: true }))
      .toHaveAttribute('aria-current', 'page')
  }
})
```

**完成条件：** 原页面仍可回退；新工程能构建，五个路由实际可用，尚未迁入的业务不能标为已完成。

### Task 3：建立 API、SSE 与共享模型状态

**新增：** shared/api、features/chat/api.ts/sse.ts、features/notes/api.ts、features/models/api.ts/store.ts；对应 api.spec.ts/sse.spec.ts/model-state.spec.ts。

- [ ] 从三个后端 schemas 和现有请求处逐项建立 TS 合同；API 层负责 JSON、204、网络错误及 detail/error/message 提取，不对写请求自动重试。
- [ ] 抽离现有 SSE 行为到 `consumeSse(stream, onEvent)`；onEvent 接收 `{event: string, data: unknown}`，调用端先按事件校验数据，不把协议判断散落在组件内。
- [ ] fixtures 覆盖 conversation、多个 token、sources、answer、draft 和工具事件；分别模拟 UTF-8 字节分片、空行分片、断流、非 2xx，验证 answer 替换 token 缓冲且引用保留。
- [ ] models store 复用现有状态转换与轮询条件；实现刷新、测试、保存、启用、删除、切换与重建请求，保留 revision 和 active 限制。
- [ ] 配置 Vite 开发代理，实际验证草稿保存和模型写请求的 Host／Origin 配对正确；通过代理发送外部 Origin 仍须拒绝，后端跨源拒绝测试仍须通过。

**完成条件：** HTTP／SSE 及维护状态可独立验证；API 地址、字段、业务动作与旧实现一致。

### Task 4：迁移 Assistant 全部行为

**新增：** features/chat 剩余组件／store、shared/ui、chat-state.spec.ts/citations.spec.ts/layout.spec.ts、assistant.spec.ts/drafts-citations.spec.ts。
**修改：** AssistantPage.vue、shared/navigation.ts。

- [ ] 先迁移会话列表和消息展示，逐项保持 F01–F03；再接输入和 SSE。用发起时会话 ID 和请求序号隔离回包。
- [ ] 将 `localizeCitations/locateQuote` 原算法抽离；为完整匹配、空 quote、找不到引文、编号重排建立测试。迁移选区与滚动时等待 Vue DOM 更新。
- [ ] 迁移 citation／draft 双模式及 F05–F08。保存草稿只调 PUT draft，同意才调 review；更多动作菜单按旧条件显示；保存失败不继续审批。
- [ ] 接入按会话快照、切换确认和 beforeunload；取消离开不能丢正文。保留临时会话首次返回正式 ID 的快照转移。
- [ ] 迁移分栏宽度算法与键盘操作，沿用存储 key；覆盖非法存储值、窗口变窄、拖拽／键盘限值。
- [ ] 保留原模型快捷操作组件位置和能力，连接 models store；完整设置内容由 Task 6 实现复用。
- [ ] 浏览器验证：打开历史引用能选中片段；编辑草稿后同意提交编辑后的正文；拒绝不写笔记；切换会话不串面板；流式期间切换一级页面再返回仍显示该轮结果。

**完成条件：** F01–F09、F16 的 Assistant 部分通过；不能用“聊天能发送”代替完整迁移验收。

### Task 5：迁移 Library 与跨页面保存一致性

**新增：** features/notes/store.ts 与三个组件、library.spec.ts。
**修改：** LibraryPage.vue、NotePane.vue、shared/navigation.ts。

- [ ] 按原 Documents 层级迁移目录树、菜单、索引芯片、正文 textarea 和 Markdown 预览；marked 通过 npm 引入并锁版本。
- [ ] 迁移 F10–F13 的新建、保存、重命名、删除、移动／拖拽和确认；JSON from/to 及一级目录限制不变。
- [ ] 保留同步滚动、Ctrl/Cmd+S、保存提示、未保存标记；route guard 同时覆盖顶部导航及浏览器后退。
- [ ] 引用保存、草稿批准、移动／重命名后刷新相关目录和统计缓存；不覆盖 Library 未保存正文。
- [ ] 浏览器验证完整操作链：新建目录→新建笔记→编辑预览→保存→补建索引→拖拽移动→重命名→删除，另测取消确认和 API 失败不丢编辑。

**完成条件：** F10–F13 全部保留，原 `/documents` 能进入 Library；不把树形编辑页面改为另一个产品形态。

### Task 6：迁移 Settings 并复用快捷操作

**新增：** features/models 的四个组件、settings.spec.ts。
**修改：** SettingsPage.vue、AssistantPage.vue。

- [ ] 逐项搬迁 model-settings.js 的表单字段、凭据选择、连接验证结果和配置列表动作；Settings 与 Assistant 弹层共用组件／store，不能用“跳设置”替掉全部原快捷能力。
- [ ] 保留保存但不启用、保存并启用、切换已有配置、当前配置编辑／删除限制、错误和 expected_revision 冲突处理。
- [ ] 迁移向量候选、availability 原因、当前状态、重建任务进度与失败反馈；只显示后端已实际提供的阶段／计数。
- [ ] 验证切换 Settings↔Assistant 不产生重复轮询；后台任务期间跨页禁用聊天和写入；返回可见页刷新服务端状态。
- [ ] 浏览器验证保存失败保留表单、启用失败保留原 active、过期 revision 提示刷新、当前模型索引不可用时修复、任务失败后可重新操作。

**完成条件：** F14–F16 通过，现有模型操作没有因页面归属变化而丢失。

### Task 7：填充最小 Home、Records 空状态与统一美化

**修改：** HomePage.vue、RecordsPage.vue、AppShell.vue、styles、navigation.spec.ts。

- [ ] Home 只呈现第 3 节已定义的真实笔记／索引概览和四个导航；用 notes/models store，避免新建统计 API。
- [ ] 单独处理加载、空数据、接口失败、索引不可用与维护状态；未知数据不显示为零。
- [ ] Records 使用简单空状态说明，不增加未来流程；只通过页面容器和可扩展布局预留空间。
- [ ] 统一现有页面的间距、字体、边框、按钮和焦点态；保留正文、工具轨迹、审批动作、设置字段。
- [ ] 在 1440px、1024px、窄屏分别核对导航、分栏、菜单与编辑可达性；正文宽度不足时允许折叠面板，不能使功能无法访问。

**完成条件：** 五页可使用或明确空状态，没有模拟业务数据；美化前后 F01–F16 保持。

### Task 8：部署接入、总回归与文档交接

**修改：** Dockerfile、.dockerignore、必要的 pyproject.toml、bootstrap/settings.py 默认模式、README.md、docs/guides/zh/local-dev.md、docs/guides/zh/getting-started.md、docs/architecture/frontend.md、docs/product/frontend-architecture.md、docs/plans/README.md、结果文档。

- [ ] 增加 Node 构建阶段和产物 COPY，保留现有 Python 依赖、模型预热、entrypoint、卷与数据库初始化行为。
- [ ] 验证本地前后端开发、生产产物由 FastAPI 托管、Docker 构建运行三条路径；不得用 Vite dev 正常代替生产部署通过。
- [ ] 更新模板断言测试：legacy 模式继续覆盖旧模板；Vue 模式验证路由和产物；草稿菜单／分栏等 DOM 行为移到浏览器测试，保留后端审批和存储测试。
- [ ] 运行第 6 节命令与验收矩阵，记录真实输出、版本、截图和限制。未运行项不可勾选。
- [ ] 全部迁移回归通过后默认切 vue；执行 legacy 回退演练，确认笔记、会话、待审草稿与模型配置不变。
- [ ] 更新现行架构为实际落地结构，上层产品文档记录已确认的顶部顺序和范围；不把整个 V2 或 V2.2／V2.3 标为已验收。

**完成条件：** Qoder 的交付包含实现、测试证据、启动／构建说明与回退办法。只完成脚手架不算 V2.7 本计划完成。

## 6. 验证命令与验收矩阵

以下是执行阶段命令，不代表本次已运行。npm scripts 由 Task 2 定义；浏览器环境用隔离测试 API fixtures 验证异常分支，再用真实 FastAPI 和测试数据完成联调。

```powershell
# 仓库根目录
uv run pytest tests -q
npm --prefix frontend ci
npm --prefix frontend run type-check
npm --prefix frontend run test:unit
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
docker compose build app
```

Playwright 配置用 Vite webServer 和 `frontend/tests/fixtures/api.ts` 的合同响应运行稳定回归，SSE 用可控响应模拟分片；生产路由/静态资源由 Python 集成测试及构建后的真实浏览器验收共同覆盖。真实联调启动沿用项目现有配置和 `uv run python main.py`；Docker 启动按现有指南执行，不能为了测试清空现有数据库或卷。

| 验收项 | 成功证据 |
|---|---|
| 功能保留 | F01–F16 每行都有对应新入口和测试或可重复手动步骤 |
| 路由与资源 | 五页直达／刷新、documents 兼容、浏览器前后退；未知 API/静态文件返回 404 |
| SSE | 多事件与分片、最终 answer 替换、引用更新、异常释放锁、跨页继续显示 |
| 草稿／正式笔记边界 | 保存草稿不写 Markdown；同意写编辑后的正文；拒绝不写；失败可重试 |
| 引用 | 原有 quote 匹配、选中滚动、文件级引用、失配提示、历史恢复均保留 |
| 状态隔离 | 快速切换不串内容；取消离开保留正文；跨组件保存不静默覆盖未保存编辑 |
| 目录／编辑 | 全部 CRUD、一级目录、拖拽移动、预览同步、快捷键、索引状态 |
| 模型维护 | 保存/启用区分、凭据处理、revision 冲突、流式和维护锁、任务轮询恢复 |
| Home／Records | 全部数字可反查现有接口；没有复习假数据或未实现操作按钮 |
| 构建／回退 | npm 构建、FastAPI 托管、Docker、legacy 模式实际验证 |

结果文档中必须区分：自动测试通过、人工验证通过、环境阻塞、已知旧问题、此次新增问题。不得以截图存在代替按钮行为验证，也不得因旧的模板字符串断言不适配 Vue 就直接删掉相应功能覆盖。

## 7. 官方技术参考与使用边界

- [Vue 官方快速开始](https://vuejs.org/guide/quick-start.html)：Vue SFC 工程、Vite 构建与 Node 前置要求；执行时锁定实际兼容版本。
- [Vue Router history 模式](https://router.vuejs.org/guide/essentials/history-mode.html)：HTML5 history 需要服务端页面回退；本项目限定页面白名单，避免影响 API。
- [Vite 开发服务器配置](https://vite.dev/config/server-options.html)：开发代理配置；本项目需额外保留已有同源写校验。

以上参考只支持构建与接入方式，业务行为以仓库代码和本计划功能保留清单为准。

## 8. 给 Qoder 的执行入口

请先阅读本计划、CLAUDE.md 和现行前端代码，按 Task 1–8 顺序推进。每完成一个任务，在结果文档列出修改文件、通过的功能编号、测试命令与结果。遇到接口或现有能力与计划不同，先以实际代码修正迁移清单；涉及改变已有用户行为或引入新业务时记录差异，不自行扩展范围。保持当前已有页面功能完整，不执行 V2.2／V2.3 优化或其他 V2／V3 业务开发。
