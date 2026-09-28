# frontend

NoteAgent 的现行界面：Vue 3 + TypeScript + Vite 单页应用，顶部四个工作入口
（Home / Assistant / Records / Library）加右上角设置齿轮，共五个页面。构建产物由 FastAPI 从
`src/noteagent/web/dist/` 托管，挂在 `/ui-assets/` 下。

## 环境

Node 20.19+ 或 22.12+（Vite 7 的 `engines`，写在 `package.json` 里）。
本机开发用的是 22.16.0；镜像里的构建阶段用 Node 24，两者都在范围内。

## 常用命令

```bash
npm ci                # 按 lockfile 安装（首次或依赖变更后）
npm run dev           # 开发服务器 http://127.0.0.1:5173，接口代理到 127.0.0.1:8000
npm run build         # 先 vue-tsc 类型检查，再 vite build，产物写到 ../src/noteagent/web/dist
npm run type-check    # 只做类型检查
npm run test:unit     # Vitest：状态与协议（不需要后端）
npm run test:e2e      # Playwright：交互回归（用固定 fixtures，不需要后端）
```

`test:e2e` 用本机已安装的 Edge（Chromium 内核），不需要 `npx playwright install`。
要改用 Playwright 钉住的 Chromium：执行 `npx playwright install chromium`，
再把 `playwright.config.ts` 里的 `channel: 'msedge'` 去掉。

## 开发时的后端

`npm run dev` 会把 `/chat`、`/conversations`、`/notes`、`/model-settings` 代理到
`http://127.0.0.1:8000`，所以先起后端：

```bash
python main.py            # 需要 DATABASE_URL 指向可用的 PostgreSQL
```

代理刻意使用 `changeOrigin: false`：后端 `require_same_origin` 比较 Origin 的 netloc 与 Host，
改写任一侧都会让写请求被 403。

## 结构

```text
src/
  main.ts / App.vue / router.ts     入口、根组件、页面路由
  layouts/AppShell.vue              顶部主导航＋设置齿轮、全局对话框与浮层
  pages/                            五个页面模块（Settings 用 ?section= 选分类）
  features/{chat,notes,models}/      领域状态（store.ts）与组件
  features/settings/                设置分类定义、分类布局与两个分类面板
  shared/{api,navigation,ui,unsaved-guard}
tests/
  unit/                             Vitest（纯逻辑与 store）
  e2e/                              Playwright（用户行为）
  fixtures/api.ts                   单测与 e2e 共用的固定响应
```

约定：组件只渲染与转发交互，规则放 `store.ts` 或纯函数模块；协议判断集中在
`features/chat/sse.ts` 与 `shared/api/http.ts`，不散落到组件里。
