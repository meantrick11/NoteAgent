# Settings 入口调整与分类预留执行记录（2026-09-28）

本文件是 [2026-09-28 Settings 入口调整与分类预留执行计划](./2026-09-28-settings-navigation-and-sections.md) 的执行记录：
基线、逐任务证据、未执行项。产品语义以 [Settings 分类与未来个人中心边界](../product/settings-architecture.md) 为准；
现行界面结构见 [frontend.md](../architecture/frontend.md)。

**范围：** 只改前端 Vue 应用（`frontend/`）与相关文档。未改后端、接口、数据库、模型配置、Agent、
生成／检索逻辑，未升级依赖，未改 legacy 页面。

---

## 1. 执行基线

| 项 | 值 |
|---|---|
| 检查时间 | 2026-09-28T16:55:33+08:00 |
| 分支 | `feat/vue-frontend-initialization` |
| HEAD | `dc90585232ff456cbbb0934b017575192d163574`（docs(architecture): stop describing the frontend as a single template） |
| 工作区 | 保留既有未提交改动（四目录文档整理一轮的改动与未跟踪文件），本轮不还原、不覆盖 |
| 影响范围 | `frontend/src`、`frontend/tests`、`docs/**` 相关说明 |

### 1.1 基线命令与结果

命令均带 `--prefix frontend`，在仓库根执行：

| 命令 | 结果 |
|---|---|
| `npm --prefix frontend run type-check` | 通过（`vue-tsc -b --force` 无输出） |
| `npm --prefix frontend run test:unit` | 7 文件 / 114 用例全部通过 |
| `npm --prefix frontend run test:e2e -- tests/e2e/navigation.spec.ts tests/e2e/settings.spec.ts` | 20 用例全部通过（msedge，本机 Edge，无需安装浏览器） |

基线数据是本轮实测，不复制 [上一份结果文档](./2026-09-28-vue-frontend-initialization-results.md) 的成绩。

### 1.2 基线代码状态

| 文件 | 基线情况 |
|---|---|
| `frontend/src/shared/navigation.ts` | 单一 `NAV_ITEMS`（五项）；Home 快捷入口与顶部导航共用同一列表 |
| `frontend/src/layouts/AppShell.vue` | `nav.app-nav` 循环输出五个 `RouterLink` |
| `frontend/src/pages/HomePage.vue` | `NAV_ITEMS.filter(item => item.name !== 'home')` 作为快捷入口 |
| `frontend/src/router.ts` | `PAGE_ROUTES` 五页，注释声明与 `NAV_ITEMS` 一一对应 |
| `frontend/src/pages/SettingsPage.vue` | 一次性纵向展示聊天模型与向量模型两张 `.settings-card` |
| `frontend/tests/unit/navigation.spec.ts` | 断言五导航与 `PAGE_ROUTES` 完全一致 |
| `frontend/tests/e2e/navigation.spec.ts` | 顶部文字 Settings、窄屏五入口、`toHaveCount(5)` |
| `frontend/tests/e2e/settings.spec.ts` | 用 `.settings-card` 定位表单，两类内容同页可见 |

---

## 2. 逐任务结果

### Task 1：记录基线并分离入口定义

**状态：** 已完成。

**改动文件**

| 文件 | 改动 |
|---|---|
| `frontend/src/shared/navigation.ts` | `NAV_ITEMS` 拆为 `PRIMARY_NAV_ITEMS`（四项）／`SETTINGS_ENTRY`／`HOME_SHORTCUTS`；`NAV_ITEMS` 已无引用并删除 |
| `frontend/src/layouts/AppShell.vue` | 顶部改为 `.app-header`＝主导航（四链接）＋工具区齿轮；`RouterView`／`ConfirmDialog`／`SaveToast` 原样保留 |
| `frontend/src/pages/HomePage.vue` | 快捷入口改读 `HOME_SHORTCUTS` |
| `frontend/src/router.ts` | 注释改为「页面路由与 `PRIMARY_NAV_ITEMS`／`SETTINGS_ENTRY` 对应」，路由本身未变 |
| `frontend/src/styles/base.css` | `.app-nav` 让位为 `.app-header` 容器，新增 `.app-nav-tools` / `.app-icon-link` |
| `frontend/tests/unit/navigation.spec.ts` | 改为四主导航＋设置入口的合同，`PAGE_ROUTES` 仍为五页，`/documents` 重定向仍在 |
| `frontend/tests/e2e/navigation.spec.ts` | 主导航断言改四项；设置改由齿轮进入；窄屏改 320/375px；Home 设置快捷卡单独验证 |
| `frontend/tests/e2e/library.spec.ts` | 「未保存时离开 Library 会先问」的触发入口由顶部 Settings 文字链接改为齿轮（业务断言未动） |
| `frontend/tests/e2e/settings.spec.ts` | 「Settings 与 Assistant 是同一份状态」用例的返回入口改为齿轮（业务断言未动） |

**实现要点**

- 齿轮是 `RouterLink`（非可点击 `div`）：`aria-label="设置"`、`title="设置"`，内嵌 SVG 标注 `aria-hidden="true"`，
  因此可 Tab 聚焦、Enter 触发，激活时由 `router-link-exact-active` 给出选中态。
- 齿轮位于主导航之外的工具区，所以 `/settings` 下四主导航均不误选（`当前页有唯一选中态` 用例仍通过）。
- `router-link-exact-active` 在 vue-router 4 中比较匹配记录与 params，**不比较 query**，
  因此 `/settings?section=retrieval` 下齿轮同样保持选中；分类选中态不依赖该 class（见 Task 2）。

**验证**

- `npm --prefix frontend run type-check`：通过。
- `npm --prefix frontend run test:unit`：7 文件 / 116 用例通过（`navigation.spec.ts` 由 3 条扩为 5 条合同用例）。
- `npm --prefix frontend run test:e2e -- tests/e2e/navigation.spec.ts`：11 用例通过。
- `npm --prefix frontend run test:e2e -- tests/e2e/settings.spec.ts tests/e2e/library.spec.ts`：全部通过，
  证明入口改动没有削弱未保存离开保护与设置页业务断言。

### Task 2：分类结构与现有内容归位

**状态：** 已完成。

**新建文件**

| 文件 | 内容 |
|---|---|
| `frontend/src/features/settings/sections.ts` | 静态分类定义（七个 ID／标题／`status`）、`AVAILABLE_SETTINGS_SECTIONS`、`resolveSettingsSection(value)` |
| `frontend/src/features/settings/SettingsLayout.vue` | 两栏骨架：`nav[aria-label="设置分类"]` ＋ `<slot name="content">` |
| `frontend/src/features/settings/ModelConnectionsSection.vue` | 包装 `ChatProfiles`；标题／说明按产品设计 |
| `frontend/src/features/settings/RetrievalSection.vue` | 承接原向量摘要、`STAGE_TEXT` 进度行与 `EmbeddingSettings` |
| `frontend/tests/unit/settings-sections.spec.ts` | 计划 §Task 2 给定的两条合同用例，逐字实现 |

**修改文件**

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/SettingsPage.vue` | 按 `route.query.section` 选类；两个可用分类**同时挂载**、`v-show` 切换；无效／数组／reserved 值 `router.replace` 到 `models` 且保留其他 query；标题改为「设置」 |
| `frontend/tests/e2e/settings.spec.ts` | 新增 `section(page, id)` 按 `[data-settings-section]` 定位；原来的「聊天配置与向量候选同页」用例拆成「默认分类」与「检索分类」两条；向量用例显式访问 `?section=retrieval`；`.settings-card.first()` 全部移除 |

**实现要点**

- `resolveSettingsSection` 只对字符串 `'retrieval'` 返回 `retrieval`，其余（`undefined` / `null` / `''` /
  未知值 / reserved 值 / 数组）一律 `models`；不引入配置 schema 或远程注册。
- 分类是 `RouterLink` ＋ `:aria-current`，选中态由页面解析出的 `activeSection` 驱动，不依赖 `router-link-exact-active`
  （该 class 忽略 query，无法区分两个分类）。
- 两个可用分类都用 `v-show`（`display:none`），切分类不卸载 `ChatProfileForm`，未提交文本不丢；
  隐藏区不可聚焦、不被读屏读取（`display:none` 的既有语义）。
- 七个 ID 中只有 `models`／`retrieval` 进入导航；`general`／`editor`／`data`／`recording`／`organization`
  只存在于静态定义与文档，不渲染空菜单、假数值或空白表单。
- 页面 `onMounted` 仍是 `fetchStatus(true)` ＋ `loadCandidates()`，每次进入页面一次；分类切换不触发任何初始化或轮询。
  全局 `models.init()` 仍在 `App.vue` 根部唯一一份，`EmbeddingSettings`／`ChatProfiles` 的保存、连接测试、
  切换与删除逻辑全部未改。

**验证**

- `npm --prefix frontend run type-check`：通过。
- `npm --prefix frontend run test:unit`：8 文件 / 120 用例通过，其中 `settings-sections.spec.ts` 4 条
  （开放分类、未知/未开放/数组回默认、七个 ID 与标题、预留分类不能经 URL 进入）。
- `npm --prefix frontend run test:e2e -- tests/e2e/settings.spec.ts`：10 用例通过。

### Task 3：状态与跨页面回归

**状态：** 已完成。

**新增／调整的用例**

`frontend/tests/e2e/settings.spec.ts`（新增 6 条）：

| 用例 | 覆盖 |
|---|---|
| 分类深链接、刷新与前进后退都还原分类 | `/settings?section=retrieval` 直达、刷新后仍是检索分类、`goBack`／`goForward` 跟随，两分类的标题与 `aria-current` 都对 |
| 无效或未开放分类 replace 成默认，且不新增历史项 | `?section=general&from=home` → `section=models` 且 `from=home` 保留；`goBack` 直接回到进入设置前的 `/library`，没有多余历史项 |
| 切换分类不丢模型表单，不自动保存 | 计划给定的原样用例：写入 `#ms-label` → 切检索 → 切回模型，值仍在；`calls` 中没有非 GET 请求 |
| 切换分类不重复初始化模型状态 | 用 `stubApi` 新增的 `statusReads()`／`candidateReads()` 计数：切换前后 `/model-settings` 与 `/model-settings/embeddings` 请求数不变 |
| 重建中切回检索分类，进度继续更新 | 切到模型分类期间 `jobPolls()` 继续增长，回到检索仍看到「正在切换到 ……」 |
| 齿轮与分类都能用键盘操作，当前项可识别 | 真实 Tab 走位（非 `focus()` 直调）到齿轮，Enter 进入 `/settings`；继续 Tab 到「检索与索引」并 Enter，`aria-current` 只在该项；从主导航回 Home 后 URL 是 `/`，没有残留 query |

`frontend/tests/e2e/assistant.spec.ts`（新增 1 条）、`frontend/tests/e2e/library.spec.ts`（Task 1 已改入口）：

| 用例 | 覆盖 |
|---|---|
| 未保存时点顶部齿轮离开 Assistant 也会先问 | 齿轮触发原「未保存修改」确认；取消后 URL 与正文不变，确认放弃才真的到 `/settings` |
| 未保存时离开 Library 会先问，取消则留在原处 | 原有用例，触发入口由顶部 Settings 文字链接换成齿轮，业务断言未动 |

`frontend/tests/e2e/navigation.spec.ts` 侧：四主导航断言、齿轮进入设置、Home 设置快捷卡仍有效、
320/375px 下主导航可横向滚动且齿轮不被挤走、`1440/1024` 宽度下主导航为四项。

**业务断言未删**：保存与保存并启用的区别、revision 冲突保留输入、当前启用配置只能「保存并启用」、
Key 不回显、连接测试结论、重建并切换的请求体与进度、Settings 与 Assistant 共享状态——全部保留，
只把定位从依赖顺序的 `.settings-card.first()` 换成 `[data-settings-section]` 面板，把向量用例改走 `?section=retrieval`。
原来一条「聊天配置与向量候选同页可见」的用例按分类拆成两条，覆盖没有减少。

**视觉核对发现的一处问题**：桌面截图里页面说明与「模型与连接」的分类说明重复了同一句
「与 Assistant 输入框下方的模型入口是同一份数据」。已把页面说明收敛为「管理模型连接、检索与应用偏好。」，
共享状态那句只留在模型分类里（`frontend/src/pages/SettingsPage.vue`）。

---

## 3. 总检查（Task 4）

见 §4 命令结果与 §5 未执行项。

---

## 4. 命令结果（2026-09-28）

| 命令 | 结果 |
|---|---|
| `npm --prefix frontend run type-check` | 通过 |
| `npm --prefix frontend run test:unit` | 8 文件 / 116 用例通过 |
| `npm --prefix frontend run test:e2e -- tests/e2e/navigation.spec.ts tests/e2e/settings.spec.ts` | 27 用例通过 |
| `npm --prefix frontend run test:e2e` | 53 用例通过 |
| `npm --prefix frontend run build` | 通过（`vue-tsc -b` ＋ `vite build`） |

浏览器：Playwright 默认 `channel: msedge`（本机 Edge），未额外安装浏览器，未改测试框架。
环境限制：本机未起后端，e2e 全部走 `tests/fixtures` 的固定响应拦截；e2e 使用 Vite 开发服务器。

---

## 5. 未执行项与边界

- 未运行 Python 测试：本轮无后端改动，按计划不强制重跑 pytest。
- 未运行任何 LLM 付费评测（prompt / rag eval）。
- 未实现 `general`／`editor`／`data`／`recording`／`organization` 任何界面；预留仅存在于
  `sections.ts` 的静态条目与产品文档，不构成上线功能。
- 未引入个人中心、账号、多用户、RBAC、主题／语言／备份／同步／采集等能力，未新增依赖。
- 未改 legacy 页面与 `FRONTEND_MODE=legacy` 回退路径。
