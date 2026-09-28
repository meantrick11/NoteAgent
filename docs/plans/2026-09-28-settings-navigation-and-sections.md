# Settings 入口调整与分类预留执行计划

> **交接对象：Qoder，待执行。** 用户手动交接；本次只完成设计和计划，不修改前端代码。按任务顺序执行，在独立结果文档勾选并记录证据。

> **执行状态（2026-09-28）：已执行完毕。** 逐任务证据见
> [执行记录](./2026-09-28-settings-navigation-and-sections-results.md)；本文步骤与勾选框保留为原始规格，未回改。

**Goal：** 将已实现 Vue 应用的 Settings 文字导航改为右上角齿轮，将设置页组织为两个可用分类，并为后续配置预留简单结构，完整保留现有功能。

**Architecture：** 保留 `/settings` 页面路由，以 query 表达分类；主导航、Home 快捷入口与页面路由分别定义。设置布局复用现有 models 组件和 store，不新建后端或第二套模型状态。

**Tech Stack：** 仓库已安装的 Vue、TypeScript、Vue Router、Pinia、Vitest、Playwright；无需升级依赖。

**Spec：** [Settings 分类与未来个人中心边界](../product/settings-architecture.md)。本计划是 Vue 初始化后的增量，不重新执行 [原初始化计划](2026-09-28-vue-frontend-initialization.md)。

## 1. 已核查的代码与约束

| 文件 | 当前情况 | 本轮处理 |
|---|---|---|
| `frontend/src/shared/navigation.ts` | NAV_ITEMS 含五项；Home 和顶部共用 | 分离主导航、设置入口和 Home 快捷入口 |
| `frontend/src/layouts/AppShell.vue` | nav 循环输出五项 | 四文字项＋独立齿轮；保留 RouterView、ConfirmDialog、SaveToast |
| `frontend/src/pages/HomePage.vue` | NAV_ITEMS.filter 排除 home | 改用独立快捷入口，保留四个跳转 |
| `frontend/src/router.ts` | PAGE_ROUTES 包括五页；与导航有一一对应注释 | 保留五路由，更新注释及测试，不新增后端路径 |
| `frontend/src/pages/SettingsPage.vue` | 两张配置卡片同时展示，并含向量摘要 | 分类容器；仍复用已有配置组件 |
| `frontend/src/features/models/{ChatProfiles,ChatProfileForm,EmbeddingSettings,ModelQuickControls}.vue` | 表单状态局部保存，Settings/Assistant 共用 | 不重写操作，仅为布局必要时调整包装 |
| `frontend/src/features/models/store.ts` | 唯一配置／busy／轮询来源 | 沿用，禁止在分类中重复 init |
| `frontend/src/shared/unsaved-guard.ts` | 保护 Assistant／Library；相同 path 直接通过 | 保留原保护；Settings 分类保留表单靠不卸载内容实现 |
| `frontend/tests/unit/navigation.spec.ts` | 断言五导航与路由完全一致 | 调整为四主导航＋设置路由仍存在的合同 |
| `frontend/tests/e2e/{navigation,settings}.spec.ts` | 顶部 Settings 文本、两卡片同时可见和 `.settings-card` 选择器 | 更新路径及作用域，保留所有业务断言 |

所有路径相对仓库根目录。执行时先复核最新代码，保留用户／其他执行者的工作区改动。不编辑 notes、数据库、模型配置、Agent、生成／检索逻辑。旧 legacy 页面不参与此次外观修改。

## 2. 明确实现合同

### 2.1 导航

在现有 navigation.ts 中使用以下导出，更新所有消费者，移除已无引用的 NAV_ITEMS；NavItem 类型沿用：

```ts
export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  { name: 'home', label: 'Home', path: '/' },
  { name: 'assistant', label: 'Assistant', path: '/assistant' },
  { name: 'records', label: 'Records', path: '/records' },
  { name: 'library', label: 'Library', path: '/library' },
]
export const SETTINGS_ENTRY: NavItem = {
  name: 'settings', label: 'Settings', path: '/settings',
}
export const HOME_SHORTCUTS: readonly NavItem[] = [
  ...PRIMARY_NAV_ITEMS.filter(item => item.name !== 'home'), SETTINGS_ENTRY,
]
```

AppShell 使用 header 包含主导航与工具区。主导航 aria-label 保持“主导航”，只含四个链接；工具区独立齿轮 RouterLink 带 `aria-label="设置"`、`title="设置"`，SVG aria-hidden，不能做成没有键盘支持的可点击 div。Settings 激活时齿轮有选中态且四主导航均不误选；Home 快捷卡仍使用 Settings 标签。

### 2.2 分类

新增 `frontend/src/features/settings/sections.ts`：静态条目含 `id/title/status`，status 为 `available | reserved`。七个 ID 和标题完全采用产品设计 §3。导出 SETTINGS_SECTIONS、AVAILABLE_SETTINGS_SECTIONS，以及 `resolveSettingsSection(value: unknown): 'models' | 'retrieval'`。后者只有输入 retrieval 时返回 retrieval，其余返回 models。不能添加通用配置 schema 或远程注册服务。

SettingsPage 根据 `route.query.section` 选类；裸路径按默认 models 显示，不强制增加 query。对提供但无效、数组或 reserved 值，用 router.replace 写 models 并保留其他 query；分类点击用 RouterLink query 导航，因此服务端 `/settings` 不变。

新增 `SettingsLayout.vue` 负责分类导航和内容插槽，`ModelConnectionsSection.vue` 包装 ChatProfiles，`RetrievalSection.vue` 承接原向量摘要、STAGE_TEXT 显示和 EmbeddingSettings。文件放 `features/settings/`。

两个可用 section 均保持挂载，用 v-show 显示当前内容，避免切分类丢失 ChatProfileForm 的局部字段。隐藏区域不可被键盘聚焦或读屏读取（v-show 的 display:none），不新增持久化。页面 onMounted 的 fetchStatus/loadCandidates 仍仅每次进入页面调用一次；分类切换不再请求初始化，不重启轮询。

新增分类不触发保存、连接测试、切换模型或重建。原表单显式按钮及请求语义全部保留。只显示两个可用分类，reserved 不进入导航、不创建组件和空白表单。

## 3. 执行任务

### Task 1：记录基线并分离入口定义

**修改：** navigation.ts、AppShell.vue、HomePage.vue、router.ts 注释、必要的 styles/base.css、tests/unit/navigation.spec.ts、tests/e2e/navigation.spec.ts。
**新建：** `docs/plans/2026-09-28-settings-navigation-and-sections-results.md`。

- [ ] 记录 git status、当前提交与实际文件；先运行 type-check、unit 和 navigation/settings 浏览器用例记录基线，不复制旧报告成绩。
- [ ] 先调整单测：主导航精确四项，Home 快捷入口仍四项且含 settings；PAGE_ROUTES 仍是五页，覆盖主导航和设置入口；documents 兼容不变。
- [ ] 按 §2.1 实现入口分离与齿轮，保留布局里的全局弹窗与 toast；搜索 NAV_ITEMS 确认所有消费者已更新。
- [ ] 修改浏览器导航用例：从每个页面用齿轮进入设置；Home Settings 卡仍有效；320/375px 下主导航可横向滚动且齿轮可点击。

**完成条件：** 设置可达性不减少，四主导航和 Home 四快捷入口互不误删。

### Task 2：分类结构与现有内容归位

**新建：** features/settings/sections.ts、SettingsLayout.vue、ModelConnectionsSection.vue、RetrievalSection.vue、tests/unit/settings-sections.spec.ts。
**修改：** SettingsPage.vue、tests/e2e/settings.spec.ts。

- [ ] 为分类过滤、默认／未知／reserved／数组值解析编写如下单测，再实现 resolver 与条目定义。

```ts
import { describe, expect, it } from 'vitest'
import { AVAILABLE_SETTINGS_SECTIONS, resolveSettingsSection } from '@/features/settings/sections'

describe('设置分类合同', () => {
  it('只开放已有能力', () => {
    expect(AVAILABLE_SETTINGS_SECTIONS.map(x => x.id)).toEqual(['models', 'retrieval'])
  })
  it('未知及未开放分类回到默认', () => {
    for (const value of [undefined, null, '', 'general', 'account', ['retrieval']]) {
      expect(resolveSettingsSection(value)).toBe('models')
    }
    expect(resolveSettingsSection('retrieval')).toBe('retrieval')
  })
})
```

- [ ] 搭建两栏分类布局和 query 导航，标题／说明按产品设计；小屏分类上移，不引入 UI 库。
- [ ] 将 ChatProfiles 移入模型分类；将当前 SettingsPage 的完整向量摘要与 EmbeddingSettings 移入检索分类。保持 indexedFiles 是片段数量、corpusFiles 是笔记数量的现有显示语义。
- [ ] 两个内容保持挂载并 v-show 切换；不动 form/store/API 保存逻辑，不删 Assistant ModelQuickControls。
- [ ] 原模型测试继续访问默认分类；向量测试显式访问 `/settings?section=retrieval`。避免 `.settings-card.first()` 等布局耦合选择器，改用带名称的 region 或 section testid。

**完成条件：** 两类内容完整可用，预留只体现在静态定义和文档，不在正式界面制造无效功能。

### Task 3：状态与跨页面回归

**修改：** tests/e2e/settings.spec.ts、navigation.spec.ts；复用现有 stubApi、fixtures；如发现本次布局引入问题，只修相关组件。

- [ ] 检验两个 query 深链接、刷新、分类前进后退；无效分类 replace 不产生额外历史循环；保留其他 query。
- [ ] 新增下面的交互用例（stubApi 是 settings.spec.ts 已有 helper）；对原表单 selector 先核对实际 ID。

```ts
test('切换分类不丢模型表单，不自动保存', async ({ page }) => {
  const stub = await stubApi(page)
  await page.goto('/settings')
  await page.getByRole('button', { name: /新增配置/ }).click()
  await page.locator('#ms-label').fill('尚未保存的配置')
  const categories = page.getByRole('navigation', { name: '设置分类' })
  await categories.getByRole('link', { name: '检索与索引', exact: true }).click()
  await categories.getByRole('link', { name: '模型与连接', exact: true }).click()
  await expect(page.locator('#ms-label')).toHaveValue('尚未保存的配置')
  expect(stub.calls.filter(x => x.method !== 'GET')).toHaveLength(0)
})
```

- [ ] 保留旧 settings.spec.ts 的保存／启用区分、revision 冲突保留输入、当前启用配置限制、Key 不回显、连接测试、重建请求与进度、Assistant 共享状态用例；只更新入口与可见区域定位。
- [ ] 检验 Settings 分类切换不增加 models.init/轮询监听；重建中回到 Assistant 仍维持原操作限制；回检索分类进度继续更新。
- [ ] Assistant／Library 有未保存内容时点击齿轮，原离开确认仍有效；取消时 URL 与正文保持不变。
- [ ] 验证齿轮及分类可用 Tab/Enter 操作，当前项可识别；主导航到 Home 不把 query 改成错误路由。

**完成条件：** 没有用删除旧业务断言换取测试通过，现有配置和编辑保护不退化。

### Task 4：总检查与文档回填

**修改：** 结果文档、docs/architecture/frontend.md、frontend/README.md（涉及导航说明时）、docs/product/settings-architecture.md、frontend-architecture.md、docs/plans/README.md。

- [ ] 执行下列现有脚本，记录真实结果及浏览器／环境限制；代码改动仅前端，不默认跑 LLM 付费评测。
- [ ] 记录桌面和窄屏截图：四入口＋齿轮、Home 快捷入口、两个设置分类；用测试数据，不展示凭据。
- [ ] 更新现行架构到实际已实现结构；产品设计从待实施改成已实施并附结果链接，计划索引按真实状态移动。
- [ ] 交付列出修改文件、通过用例、未执行项；不宣布个人中心、多用户或预留分类已实现。

```powershell
npm --prefix frontend run type-check
npm --prefix frontend run test:unit
npm --prefix frontend run test:e2e -- tests/e2e/navigation.spec.ts tests/e2e/settings.spec.ts
npm --prefix frontend run test:e2e
npm --prefix frontend run build
```

已有 Playwright 默认使用本机 Edge；沿用其配置，不为本任务无故替换浏览器或安装新测试框架。若后端无改动不强制重跑全量 Python；若实施超出计划涉及服务端，说明原因并运行相应已有测试。

## 4. 不得扩大范围

不实现主题／语言／备份／同步／采集／整理方案，不增加个人账号或多用户 API，不改变现有模型权限语义，不升级依赖，不改 legacy 页面，不清理与此任务无关的文档。预留不是上线功能；将来逐项实现时再将分类开放。

本计划按现有代码独立执行，不依赖本聊天后续消息。产品语义看 settings-architecture.md，当前实现看实际 Vue 文件；若 Qoder 已有并行修改，先对齐文件状态，不覆盖已有工作。
