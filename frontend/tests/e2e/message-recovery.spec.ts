import { expect, test, type Page } from '@playwright/test'

/**
 * B8：编辑历史消息 → 预览 → 确认回退弹窗。接口全部固定响应拦截。
 */

const CONVERSATIONS = [{ id: 'c-1', title: '你好', updated_at: '2026-09-28T10:00:00Z' }]

const MESSAGES = [
  {
    id: 'u-1',
    role: 'user',
    content: '原始问题',
    created_at: '2026-09-28T10:00:01Z',
    turn_id: 't-1',
    citations: [],
    tool_steps: [],
    editable: true,
    edit_unavailable_reason: null,
  },
  {
    id: 'a-1',
    role: 'assistant',
    content: '回答',
    created_at: '2026-09-28T10:00:02Z',
    citations: [],
    tool_steps: [],
  },
]

const MODEL_SETTINGS = {
  revision: 7,
  chat_profiles: [],
  active_chat: {
    id: 'env-default', label: '环境默认', provider: 'deepseek', model: 'm',
    base_url: '', auth_mode: 'api_key', context_window: 32768,
    has_api_key: true, credential_source: 'env',
  },
  active_embedding: {
    model_id: 'intfloat/multilingual-e5-small', resolved_revision: 'r', collection: 'c', fingerprint: 'f',
  },
  retrieval_available: true, retrieval_problem: null, retrieval_state: 'ok',
  indexed_files: 0, corpus_files: 0, busy: false, embedding_job: null,
}

test('刷新失败恢复任务仍显示重试入口', async ({ page }) => {
  const calls = await stubApi(page)
  await page.route((url) => url.pathname === '/conversations/c-1', (route) => route.fulfill({
    json: { id: 'c-1', title: 'failed', pending_draft: null, state_revision: 3,
      recovery: { ...JOB, status: 'failed', prepared_turn_id: null, error: 'index unavailable' } },
  }))
  await page.route((url) => url.pathname === '/recoveries/j-1/retry', (route) => route.fulfill({ json: JOB }))
  await page.goto('/assistant')
  await page.reload()
  const dialog = page.getByRole('dialog', { name: '确认整体回退' })
  await expect(dialog).toContainText('index unavailable')
  await dialog.getByRole('button', { name: '重试', exact: true }).click()
  await expect.poll(() => calls.some(c => c.url.endsWith('/chat'))).toBe(true)
})

const PREVIEW = {
  preview_id: 'p-1', conversation_id: 'c-1', can_apply: true, requires_confirmation: true,
  file_changes: [{ path: 'A.md', action: 'restore', target_hash: 'h0', current_hash: 'h1' }],
  folder_changes: [], conflicts: [], affected_messages: ['u-1'],
  state_revision: 3, workspace_seq: 5, content_digest: 'd', expires_at: null,
}

const JOB = {
  job_id: 'j-1', operation_id: 'op-1', conversation_id: 'c-1', status: 'succeeded',
  stage: 'succeeded', prepared_turn_id: 'run-9', error: null, retryable: true, plan: {},
}

test('state-only edit waits for confirmation after keyboard submission', async ({ page }) => {
  const calls = await stubApi(page)
  await page.route(url => url.pathname.endsWith('/recoveries/preview'), route => route.fulfill({
    json: { ...PREVIEW, requires_confirmation: false, file_changes: [], folder_changes: [] },
  }))
  await page.goto('/assistant')
  await page.getByRole('button', { name: '编辑这条消息' }).click()
  const box = page.getByRole('textbox', { name: '编辑这条消息' })
  await box.fill('state-only edited question')
  await box.press('Control+Enter')
  const dialog = page.getByRole('dialog', { name: '确认整体回退' })
  await expect(dialog.getByRole('button', { name: '确认回退并重新生成' })).toBeEnabled()
  await expect(dialog).toContainText('没有文件改动')
  expect(calls.some(c => c.url.endsWith('/recoveries') || c.url.endsWith('/chat'))).toBe(false)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.msg-row.user')).toContainText('原始问题')
  expect(calls.some(c => c.url.endsWith('/recoveries') || c.url.endsWith('/chat'))).toBe(false)
})

async function stubApi(page: Page, options: { conflict?: boolean } = {}) {
  const calls: Array<{ url: string; body: unknown }> = []
  const record = (url: string, postData: string | null) => {
    calls.push({ url, body: postData ? JSON.parse(postData) : null })
  }

  // 先注册宽泛路由，再注册更具体的：后注册的优先。
  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    (route) => {
      if (route.request().url().includes('/embeddings')) return route.fulfill({ json: [] })
      return route.fulfill({ json: MODEL_SETTINGS })
    },
  )
  await page.route(
    (url) => url.pathname === '/conversations' || url.pathname.startsWith('/conversations/'),
    (route) => {
      const url = route.request().url()
      if (route.request().method() === 'GET' && /\/conversations$/.test(url)) {
        return route.fulfill({ json: CONVERSATIONS })
      }
      if (url.includes('/messages')) return route.fulfill({ json: MESSAGES })
      return route.fulfill({
        json: { ...CONVERSATIONS[0], pending_draft: null, state_revision: 3, active_run: null, recovery: null },
      })
    },
  )
  await page.route(
    (url) => url.pathname === '/notes' || url.pathname.startsWith('/notes/'),
    (route) => route.fulfill({ json: { files: [], folders: [] } }),
  )
  await page.route(
    (url) => url.pathname === '/chat',
    (route) => {
      record(route.request().url(), route.request().postData())
      const events: Array<[string, unknown]> = [
        ['conversation', { id: 'c-1', title: '你好' }],
        ['token', '重新生成'],
        ['answer', '重新生成'],
        ['turn_complete', { status: 'completed', checkpoint_id: 'cp', state_revision: 4 }],
      ]
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(''),
      })
    },
  )
  await page.route(
    (url) => url.pathname.startsWith('/recoveries/'),
    (route) => route.fulfill({ json: JOB }),
  )
  await page.route(
    (url) => /\/conversations\/[^/]+\/recoveries$/.test(url.pathname),
    (route) => {
      record(route.request().url(), route.request().postData())
      return route.fulfill({ json: JOB })
    },
  )
  await page.route(
    (url) => url.pathname.endsWith('/recoveries/preview'),
    (route) => {
      const preview = options.conflict
        ? { ...PREVIEW, can_apply: false, conflicts: [{ path: 'A.md', reason: 'changed after the boundary' }] }
        : PREVIEW
      return route.fulfill({ json: preview })
    },
  )
  return calls
}

test('编辑消息走预览确认并续接生成', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')

  const userRow = page.locator('.msg-row.user').first()
  await userRow.getByRole('button', { name: '编辑这条消息' }).click()
  const box = page.getByRole('textbox', { name: '编辑这条消息' })
  await expect(box).toHaveValue('原始问题')
  await expect(userRow.locator('.msg-body')).toHaveCount(0)
  await expect(userRow.locator('.msg-bubble textarea')).toHaveCount(1)
  await box.fill('改过的问题')
  await box.press('Control+Enter')

  const dialog = page.getByRole('dialog', { name: '确认整体回退' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('A.md')

  // 取消不启动任何恢复。
  await dialog.getByRole('button', { name: '取消' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(userRow.locator('.msg-body')).toHaveText('原始问题')
  await expect(userRow.locator('textarea')).toHaveCount(0)
  expect(calls.some((c) => /\/recoveries$/.test(c.url))).toBe(false)

  // 再次提交并确认。
  await userRow.getByRole('button', { name: '编辑这条消息' }).click()
  await page.getByRole('textbox', { name: '编辑这条消息' }).fill('改过的问题')
  await page.getByRole('textbox', { name: '编辑这条消息' }).press('Control+Enter')
  await page.getByRole('dialog', { name: '确认整体回退' })
    .getByRole('button', { name: '确认回退并重新生成' }).click()

  await expect
    .poll(() => calls.some((c) => c.url.endsWith('/chat')), { timeout: 8000 })
    .toBe(true)
  const chatCall = calls.find((c) => c.url.endsWith('/chat'))
  expect((chatCall?.body as Record<string, unknown>)?.prepared_turn_id).toBe('run-9')
  await expect(page.getByText('请求失败')).toHaveCount(0)
  await expect(page.locator('.msg-row')).toHaveCount(3)
  await expect(page.locator('.msg-row.assistant').last()).toContainText('重新生成')
})

test('冲突只提供取消，不能强制覆盖', async ({ page }) => {
  await stubApi(page, { conflict: true })
  await page.goto('/assistant')

  const userRow = page.locator('.msg-row.user').first()
  await userRow.getByRole('button', { name: '编辑这条消息' }).click()
  await page.getByRole('textbox', { name: '编辑这条消息' }).fill('改过的问题')
  await page.getByRole('textbox', { name: '编辑这条消息' }).press('Control+Enter')

  const dialog = page.getByRole('dialog', { name: '确认整体回退' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('无法回退')
  await expect(dialog.getByRole('button', { name: '确认回退并重新生成' })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: '取消' })).toBeVisible()
})
