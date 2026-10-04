import { expect, test, type Page } from '@playwright/test'

/**
 * 草稿面板的边界回归：保存草稿只改待审状态，同意才写笔记，拒绝不写。
 * 以及引用面板两种模式的切换与覆盖菜单行为。
 */

const CONVERSATIONS = [{ id: 'c-1', title: '你好', updated_at: '2026-09-28T10:00:00Z' }]

const PENDING_DRAFT = {
  action: 'append',
  file_name: 'Go.md',
  content: '## 并发模型\n\n- goroutine\n',
  reason: '补一节',
  similar: ['Go.md'],
  existing_files: ['Go.md', 'Rust.md'],
}

const MODEL_SETTINGS = {
  revision: 7,
  chat_profiles: [],
  active_chat: null,
  active_embedding: null,
  retrieval_available: true,
  retrieval_problem: null,
  retrieval_state: 'ok',
  indexed_files: 0,
  corpus_files: 0,
  busy: false,
  embedding_job: null,
}

interface StubOptions {
  reviewResult?: unknown
  draftSaveStatus?: number
  draft?: typeof PENDING_DRAFT
}

function readBody(request: { postData: () => string | null }): unknown {
  const raw = request.postData()
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

/** 起手就带着一份待审草稿：服务端在会话详情里返回 pending_draft。 */
async function stubApi(page: Page, options: StubOptions = {}) {
  const calls: Array<{ method: string; url: string; body: unknown }> = []
  let pendingDraft = { ...(options.draft ?? PENDING_DRAFT) }
  const record = (route: {
    request: () => { method: () => string; url: () => string; postData: () => string | null }
  }) => {
    const request = route.request()
    calls.push({ method: request.method(), url: request.url(), body: readBody(request) })
  }

  // 先注册宽泛的 /chat，再注册更具体的两个；后注册的优先。
  await page.route(
    (url) => url.pathname.startsWith('/chat'),
    (route) => route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' }),
  )

  await page.route(
    (url) => url.pathname.startsWith('/chat/draft'),
    async (route) => {
      record(route)
      const status = options.draftSaveStatus ?? 200
      if (status !== 200) return route.fulfill({ status, json: { detail: 'no pending draft' } })
      const body = readBody(route.request()) as { content: string; file_name?: string }
      pendingDraft = { ...pendingDraft, content: body.content, file_name: body.file_name ?? pendingDraft.file_name }
      return route.fulfill({ json: { status: 'updated', pending_draft: pendingDraft } })
    },
  )

  await page.route(
    (url) => url.pathname === '/chat/review',
    async (route) => {
      record(route)
      return route.fulfill({
        json: options.reviewResult ?? { status: 'written', action: 'append', file_name: 'Go.md' },
      })
    },
  )

  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    (route) => route.fulfill({ json: MODEL_SETTINGS }),
  )

  await page.route(
    (url) => url.pathname === '/conversations' || url.pathname.startsWith('/conversations/'),
    (route) => {
      const url = route.request().url()
      if (/\/conversations$/.test(url)) return route.fulfill({ json: CONVERSATIONS })
      if (url.includes('/messages')) return route.fulfill({ json: [] })
      return route.fulfill({ json: { ...CONVERSATIONS[0], pending_draft: pendingDraft } })
    },
  )

  await page.route(
    (url) => url.pathname.startsWith('/notes'),
    (route) => route.fulfill({ json: { file_name: 'Go.md', content: '正文' } }),
  )

  return calls
}

test('draft footer exposes append directly and submits the chosen target', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')
  const pane = page.locator('.cite-pane')
  await expect(pane.getByRole('button', { name: '同意追加' })).toBeVisible()
  await expect(pane.getByRole('button', { name: '拒绝', exact: true })).toBeVisible()
  await expect(pane.getByRole('button', { name: /更多操作/ })).toHaveCount(0)
  await pane.getByRole('button', { name: '追加到笔记', exact: true }).click()
  await pane.getByLabel('追加到笔记', { exact: true }).selectOption('Rust.md')
  await pane.getByRole('button', { name: '追加到所选笔记' }).click()
  await expect.poll(() => calls.find(c => c.url.endsWith('/chat/review'))?.body).toMatchObject({
    action: 'override', write_action: 'append', file_name: 'Rust.md',
  })
})

test('create draft name edits in the header and persists without writing a note', async ({ page }) => {
  const calls = await stubApi(page, { draft: { ...PENDING_DRAFT, action: 'create', file_name: 'New.md' } })
  await page.goto('/assistant')
  const pane = page.locator('.cite-pane')
  await expect(pane.getByRole('button', { name: '同意新建' })).toBeVisible()
  await pane.getByRole('button', { name: '编辑草稿笔记名' }).click()
  await pane.getByRole('textbox', { name: '草稿笔记名', exact: true }).fill('Renamed.md')
  await pane.getByRole('textbox', { name: '草稿笔记名', exact: true }).press('Enter')
  await expect(pane.getByRole('button', { name: '编辑草稿笔记名' })).toContainText('Renamed.md')
  await pane.getByRole('button', { name: '保存草稿' }).click()
  await expect.poll(() => calls.find(c => c.url.endsWith('/chat/draft'))?.body).toMatchObject({ file_name: 'Renamed.md' })
  expect(calls.some(c => c.url.endsWith('/chat/review'))).toBe(false)
  await page.reload()
  await expect(pane.getByRole('button', { name: '编辑草稿笔记名' })).toContainText('Renamed.md')
  await pane.getByRole('button', { name: '编辑草稿笔记名' }).click()
  await pane.getByRole('textbox', { name: '草稿笔记名', exact: true }).fill('Cancelled.md')
  await pane.getByRole('textbox', { name: '草稿笔记名', exact: true }).press('Escape')
  await expect(pane.getByRole('button', { name: '编辑草稿笔记名' })).toContainText('Renamed.md')
  await pane.getByRole('button', { name: '同意新建' }).click()
  await expect.poll(() => calls.some(c => c.url.endsWith('/chat/review'))).toBe(true)
})

test('保存草稿只调 PUT /chat/draft，不写正式笔记', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  const textarea = pane.getByRole('textbox', { name: '面板正文' })
  await textarea.fill('## 我改过的正文\n')
  await expect(pane.getByText('未保存')).toBeVisible()

  await pane.getByRole('button', { name: '保存草稿' }).click()
  await expect(page.getByRole('status').filter({ hasText: '文件已保存' })).toBeVisible()

  const draftCall = calls.find((call) => call.url.includes('/chat/draft'))
  expect(draftCall?.method).toBe('PUT')
  expect(draftCall?.body).toMatchObject({ thread_id: 'c-1', content: '## 我改过的正文\n' })
  expect(calls.some((call) => call.url.includes('/chat/review'))).toBe(false)
  expect(calls.some((call) => call.method === 'PUT' && call.url.includes('/notes/'))).toBe(false)
})

test('同意前先把未保存正文落库，再调 review 写笔记', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await pane.getByRole('textbox', { name: '面板正文' }).fill('## 我改过的正文\n')
  await pane.getByRole('button', { name: '同意追加' }).click()

  await expect(page.locator('.msg-body', { hasText: '已写入 Go.md' })).toBeVisible()

  const urls = calls.map((call) => call.url)
  const draftIndex = urls.findIndex((url) => url.includes('/chat/draft'))
  const reviewIndex = urls.findIndex((url) => url.includes('/chat/review'))
  expect(draftIndex).toBeGreaterThanOrEqual(0)
  expect(reviewIndex).toBeGreaterThan(draftIndex)

  const review = calls[reviewIndex]
  expect(review.body).toMatchObject({ thread_id: 'c-1', action: 'approve' })
  // 审批之后草稿区收起，引用模式回到没有内容的状态。
  await expect(pane.getByText('待审批草稿')).toHaveCount(0)
})

test('保存草稿失败就不继续审批', async ({ page }) => {
  const calls = await stubApi(page, { draftSaveStatus: 409 })
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await pane.getByRole('textbox', { name: '面板正文' }).fill('改过的正文')
  await pane.getByRole('button', { name: '同意追加' }).click()

  // 失败提示出现，正文保留，且没有调用审批。
  await expect(page.getByRole('dialog', { name: '保存失败' })).toBeVisible()
  await page.getByRole('dialog', { name: '保存失败' }).getByRole('button', { name: '确认' }).click()
  expect(calls.some((call) => call.url.includes('/chat/review'))).toBe(false)
  await expect(pane.getByRole('textbox', { name: '面板正文' })).toHaveValue('改过的正文')
})

test('审批失败留下草稿与原因，可以重试', async ({ page }) => {
  const calls = await stubApi(page, { reviewResult: { error: '写盘失败' } })
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await pane.getByRole('button', { name: '同意追加' }).click()

  await expect(pane.getByText('审批失败：写盘失败')).toBeVisible()
  await expect(page.locator('.msg-body', { hasText: '审批失败：写盘失败' })).toBeVisible()
  // 草稿还在，按钮可以再点。
  await expect(pane.getByRole('textbox', { name: '面板正文' })).toHaveValue(PENDING_DRAFT.content)
  await expect(pane.getByRole('button', { name: '同意追加' })).toBeEnabled()
  expect(calls.filter((call) => call.url.includes('/chat/review'))).toHaveLength(1)
})

test('拒绝走 reject，不写笔记也不留草稿', async ({ page }) => {
  const calls = await stubApi(page, { reviewResult: { status: 'rejected' } })
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await pane.getByRole('button', { name: '拒绝' }).click()

  await expect(page.locator('.msg-body', { hasText: '已取消写入' })).toBeVisible()
  const review = calls.find((call) => call.url.includes('/chat/review'))
  expect(review?.body).toMatchObject({ thread_id: 'c-1', action: 'reject' })
  expect(calls.some((call) => call.method === 'PUT' && call.url.includes('/notes/'))).toBe(false)
})

test('replace 动作没有覆盖入口', async ({ page }) => {
  await stubApi(page)
  await page.route(
    (url) => url.pathname.startsWith('/conversations/'),
    (route) => {
      const url = route.request().url()
      if (url.includes('/messages')) return route.fulfill({ json: [] })
      return route.fulfill({
        json: {
          ...CONVERSATIONS[0],
          pending_draft: { ...PENDING_DRAFT, action: 'replace' },
        },
      })
    },
  )
  await page.goto('/assistant')

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await expect(pane.getByText('覆盖 · Go.md')).toBeVisible()
  await expect(pane.getByRole('button', { name: '同意覆盖' })).toBeVisible()
  // replace 只有一种结果，不需要"更多操作"。
  await expect(pane.getByRole('button', { name: /更多操作/ })).toHaveCount(0)
})
