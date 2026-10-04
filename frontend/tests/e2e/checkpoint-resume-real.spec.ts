import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'

let server: ChildProcess
let backend: string

test.beforeAll(async () => {
  test.setTimeout(60_000)
  const root = resolve(process.cwd(), '..')
  server = spawn(resolve(root, '.venv/Scripts/python.exe'), ['tests/support/resume_server.py'], {
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

test.afterAll(() => { server?.kill() })

test('reload exposes an interrupted checkpoint and resumes through real HTTP once', async ({ page }) => {
  await page.route((url) => url.pathname === '/chat' || url.pathname.startsWith('/conversations') || url.pathname.startsWith('/model-settings'), async (route) => {
    const original = new URL(route.request().url())
    const response = await route.fetch({ url: `${backend}${original.pathname}${original.search}` })
    await route.fulfill({ response })
  })
  const requests: unknown[] = []
  page.on('request', (request) => { if (new URL(request.url()).pathname === '/chat') requests.push(request.postDataJSON()) })
  await page.goto('/assistant')
  await expect(page.getByRole('button', { name: '继续生成', exact: true })).toBeVisible()
  await page.reload()
  const resume = page.getByRole('button', { name: '继续生成', exact: true })
  await expect(resume).toBeVisible()
  expect(requests).toHaveLength(0)
  await resume.click()
  await expect(page.locator('.msg-row.assistant')).toContainText('Recovered reply')
  await expect(resume).toHaveCount(0)
  expect(requests).toHaveLength(1)
  expect(requests[0]).toMatchObject({ run_id: expect.any(String), conversation_id: expect.any(String) })
  expect(requests[0]).not.toHaveProperty('question')
  await page.reload()
  await expect(page.locator('.msg-row.user')).toHaveCount(1)
  await expect(page.locator('.msg-row.assistant')).toHaveCount(1)
  await expect(page.locator('.msg-row.assistant')).toContainText('Recovered reply')
})
