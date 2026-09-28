import { expect, test } from '@playwright/test'

test('顶部入口顺序固定且各页面可刷新', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.getByRole('link')).toHaveText([
    'Home',
    'Assistant',
    'Records',
    'Library',
    'Settings',
  ])
  for (const [label, path] of [
    ['Assistant', '/assistant'],
    ['Records', '/records'],
    ['Library', '/library'],
    ['Settings', '/settings'],
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
})

test('当前页有唯一选中态', async ({ page }) => {
  await page.goto('/library')
  const nav = page.getByRole('navigation', { name: '主导航' })
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1)
  await expect(nav.locator('[aria-current="page"]')).toHaveText('Library')
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

test('窄屏下五个入口仍然可达', async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 720 })
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: '主导航' })
  // 横向滚动而不是隐藏入口：逐个可点且能切换。
  await nav.getByRole('link', { name: 'Settings', exact: true }).scrollIntoViewIfNeeded()
  await nav.getByRole('link', { name: 'Settings', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
})
