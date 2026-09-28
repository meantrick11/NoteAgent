import { expect, test } from '@playwright/test'

test('主导航固定四项，设置由齿轮进入且各页面可刷新', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: '主导航' })
  const gear = page.getByRole('link', { name: '设置' })
  await expect(nav.getByRole('link')).toHaveText([
    'Home',
    'Assistant',
    'Records',
    'Library',
  ])
  for (const [label, path] of [
    ['Assistant', '/assistant'],
    ['Records', '/records'],
    ['Library', '/library'],
    ['Home', '/'],
  ]) {
    await nav.getByRole('link', { name: label, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await page.reload()
    await expect(nav.getByRole('link', { name: label, exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
  }
  // 设置不在主导航里，从任意页面都能用齿轮到达并刷新。
  await gear.click()
  await expect(page).toHaveURL(/\/settings$/)
  await page.reload()
  await expect(gear).toHaveAttribute('aria-current', 'page')
})

test('当前页有唯一选中态', async ({ page }) => {
  await page.goto('/library')
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1)
  await expect(nav.locator('[aria-current="page"]')).toHaveText('Library')

  // 设置页：选中态在齿轮上，四个工作入口都不误选。
  await page.getByRole('link', { name: '设置' }).click()
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(0)
  await expect(page.getByRole('link', { name: '设置' })).toHaveAttribute(
    'aria-current',
    'page',
  )
})

test('旧地址 /documents 落到 Library', async ({ page }) => {
  await page.goto('/documents')
  await expect(page).toHaveURL(/\/library$/)
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.locator('[aria-current="page"]')).toHaveText('Library')
})

test('未知地址回到 Home', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page).toHaveURL(/\/$/)
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.locator('[aria-current="page"]')).toHaveText('Home')
})

test('浏览器前进后退跟随路由', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: '主导航' })
  await nav.getByRole('link', { name: 'Records', exact: true }).click()
  await expect(page).toHaveURL(/\/records$/)
  await page.goBack()
  await expect(page).toHaveURL(/\/$/)
  await page.goForward()
  await expect(page).toHaveURL(/\/records$/)
})

test('窄屏下四个入口可滚动，齿轮始终可点', async ({ page }) => {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 720 })
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: '主导航' })
    // 横向滚动而不是隐藏入口：逐个可点且能切换。
    await nav.getByRole('link', { name: 'Library', exact: true }).scrollIntoViewIfNeeded()
    await nav.getByRole('link', { name: 'Library', exact: true }).click()
    await expect(page).toHaveURL(/\/library$/)

    // 齿轮不被滚动的入口挤走：不滚动也能直接点到。
    const gear = page.getByRole('link', { name: '设置' })
    await gear.click()
    await expect(page).toHaveURL(/\/settings$/)
  }
})

const NOTES = {
  files: [
    { file_name: 'A.md', folder: '', mtime: 1758998400, indexed: true },
    { file_name: 'B.md', folder: '', mtime: 1758998400, indexed: true },
    { file_name: 'C.md', folder: '', mtime: 1758998400, indexed: false },
  ],
  folders: [],
}

const MODEL_SETTINGS = {
  revision: 1,
  chat_profiles: [],
  active_chat: null,
  active_embedding: null,
  retrieval_available: true,
  retrieval_problem: null,
  retrieval_state: 'ok',
  indexed_files: 2,
  corpus_files: 3,
  busy: false,
  embedding_job: null,
}

async function stubHome(page: import('@playwright/test').Page, notesStatus = 200) {
  await page.route(
    (url) => url.pathname === '/notes',
    (route) =>
      notesStatus === 200
        ? route.fulfill({ json: NOTES })
        : route.fulfill({ status: notesStatus, json: { detail: '笔记目录读取失败' } }),
  )
  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    (route) => route.fulfill({ json: MODEL_SETTINGS }),
  )
}

test('Home 显示真实笔记与索引数量，并提供四个入口', async ({ page }) => {
  await stubHome(page)
  await page.goto('/')

  const stats = page.locator('.stat')
  await expect(stats.nth(0)).toContainText('笔记总数')
  await expect(stats.nth(0).locator('.stat-value')).toHaveText('3')
  await expect(stats.nth(1).locator('.stat-value')).toHaveText('2')
  await expect(stats.nth(2).locator('.stat-value')).toHaveText('1')

  // 四个快捷入口与顶部导航指向同一批路由。
  const shortcuts = page.locator('.shortcut')
  await expect(shortcuts).toHaveCount(4)
  await expect(shortcuts).toHaveText([
    /Assistant/,
    /Records/,
    /Library/,
    /Settings/,
  ])

  await shortcuts.first().click()
  await expect(page).toHaveURL(/\/assistant$/)

  // 设置从顶部文字项移走后，Home 的设置快捷卡仍然有效。
  await page.goto('/')
  await page.locator('.shortcut', { hasText: 'Settings' }).click()
  await expect(page).toHaveURL(/\/settings$/)
})

test('Home 读不到笔记时显示错误与重试，而不是显示 0', async ({ page }) => {
  await stubHome(page, 500)
  await page.goto('/')

  await expect(page.getByText(/读取笔记目录失败/)).toBeVisible()
  await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
  // 数字区不出现，避免 0 被当成真实值。
  await expect(page.locator('.stat-value')).toHaveCount(0)
})

test('Home 在索引不可用时说清原因，而不是当成逐篇未索引', async ({ page }) => {
  await page.route(
    (url) => url.pathname === '/notes',
    (route) => route.fulfill({ json: NOTES }),
  )
  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    (route) =>
      route.fulfill({
        json: {
          ...MODEL_SETTINGS,
          retrieval_available: false,
          retrieval_state: 'missing',
          retrieval_problem: '索引 collection 不存在，需要重建。',
        },
      }),
  )
  await page.goto('/')
  await expect(page.locator('.home-note')).toContainText('索引 collection 不存在')
})

test('Records 只有空状态，没有可点的业务操作', async ({ page }) => {
  await page.goto('/records')
  await expect(page.getByText('尚未开放')).toBeVisible()
  await expect(page.getByText(/不提供任何操作/)).toBeVisible()
  // 没有按钮：不预留虚假的录制／导入等入口。
  await expect(page.locator('main button')).toHaveCount(0)
})

test('1440 与 1024 宽度下导航与内容都可达', async ({ page }) => {
  for (const width of [1440, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/library')
    const nav = page.getByRole('navigation', { name: '主导航' })
    await expect(nav.getByRole('link')).toHaveCount(4)
    await expect(page.getByRole('link', { name: '设置' })).toBeVisible()
    // 目录树、工具栏按钮与编辑区都要在视口内可用。
    await expect(page.locator('[data-notes-tree]')).toBeVisible()
    await expect(page.getByRole('button', { name: '＋ 新建笔记' })).toBeVisible()
    await expect(page.getByRole('button', { name: '保存' })).toBeVisible()
  }
})
