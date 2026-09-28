import { defineConfig, devices } from '@playwright/test'

// 用户交互回归：跑在 Vite 开发服务器上，接口用 tests/fixtures 的固定响应拦截，
// 不依赖后端是否启动，也不碰真实笔记。
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  // 用本机已安装的 Edge（Chromium 内核），不需要 `playwright install` 下载浏览器。
  // 若要改用 Playwright 钉住的 Chromium 版本：执行 `npx playwright install chromium`
  // 后把下面的 channel 去掉即可。
  projects: [
    {
      name: 'msedge',
      use: { ...devices['Desktop Chrome'], channel: 'msedge' },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173/',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
