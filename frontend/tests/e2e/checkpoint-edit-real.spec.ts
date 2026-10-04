import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'

let server: ChildProcess
let backend: string

test.beforeEach(async () => {
  test.setTimeout(60_000)
  const root = resolve(process.cwd(), '..')
  server = spawn(resolve(root, '.venv/Scripts/python.exe'), ['tests/support/resume_server.py', '--edit'], {
    cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  })
  backend = await new Promise<string>((accept, reject) => {
    // Python's retrieval imports compete with the full suite's browser workers.
    let diagnostics = ''
    server.stderr!.on('data', (chunk) => { diagnostics += chunk.toString() })
    const timeout = setTimeout(() => reject(new Error(`Isolated backend did not start: ${diagnostics}`)), 55_000)
    let output = ''
    server.stdout!.on('data', (chunk) => {
      output += chunk.toString()
      const match = output.match(/REVIEW_SERVER (http:\/\/127\.0\.0\.1:\d+)/)
      if (match) { clearTimeout(timeout); accept(match[1]!) }
    })
    server.on('error', (error) => { clearTimeout(timeout); reject(error) })
    server.on('exit', (code) => { clearTimeout(timeout); reject(new Error(`Backend exited: ${code}: ${diagnostics}`)) })
  })
  await expect.poll(async () => {
    try { return (await fetch(`${backend}/conversations`)).status } catch { return 0 }
  }).toBe(200)
})

test.afterEach(() => { server?.kill() })

test('fresh streamed message becomes editable without reloading', async ({ page }) => {
  await page.route((url) => ['/chat', '/notes'].includes(url.pathname) || url.pathname.startsWith('/conversations') || url.pathname.startsWith('/recoveries') || url.pathname.startsWith('/model-settings'), async (route) => {
    const original = new URL(route.request().url())
    const response = await route.fetch({ url: `${backend}${original.pathname}${original.search}`,
      headers: { ...route.request().headers(), origin: backend } })
    await route.fulfill({ response })
  })
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: '输入你的问题' }).fill('fresh streamed question')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const fresh = page.locator('.msg-row.user').last()
  await expect(fresh).toContainText('fresh streamed question')
  await expect(fresh.getByRole('button', { name: '编辑这条消息' })).toBeEnabled()
})

test('real checkpoint edit confirms file rollback and persists regenerated reply', async ({ page }) => {
  await page.route((url) => ['/chat', '/notes'].includes(url.pathname) || url.pathname.startsWith('/conversations') || url.pathname.startsWith('/recoveries') || url.pathname.startsWith('/model-settings'), async (route) => {
    const original = new URL(route.request().url())
    const response = await route.fetch({ url: `${backend}${original.pathname}${original.search}`, headers: { ...route.request().headers(), origin: backend } })
    await route.fulfill({ response })
  })
  await page.goto('/assistant')
  const edit = page.getByRole('button', { name: '编辑这条消息' }).first()
  await expect(edit).toBeEnabled()
  await edit.click()
  const text = page.getByRole('textbox', { name: '编辑这条消息' })
  await text.fill('edited question')
  await page.getByRole('button', { name: '重新生成', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '确认整体回退' })
  await expect(dialog).toContainText('A.md')
  await dialog.getByRole('button', { name: '确认回退并重新生成' }).click()
  await expect(page.locator('.msg-row.assistant')).toContainText('Recomputed reply')
  await page.reload()
  await expect(page.locator('.msg-row.user')).toHaveCount(1)
  await expect(page.locator('.msg-row.user')).toContainText('edited question')
  await expect(page.locator('.msg-row.assistant')).toHaveCount(1)
  await expect(page.locator('.msg-row.assistant')).toContainText('Recomputed reply')
  const response = await fetch(`${backend}/notes`)
  const notes = await response.json()
  expect(notes.files).toHaveLength(0)
})
