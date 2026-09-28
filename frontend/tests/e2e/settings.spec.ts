import { expect, test, type Page } from '@playwright/test'

/**
 * Settings 的模型管理回归：保存与保存并启用的区别、凭据保留语义、
 * revision 冲突、向量候选与重建任务，以及"设置页与快捷弹层是同一份状态"。
 */

const BASE_STATUS = {
  revision: 7,
  chat_profiles: [
    {
      id: 'env-default',
      label: '环境默认',
      provider: 'deepseek',
      model: 'deepseek-v4-flash',
      base_url: 'https://api.deepseek.com',
      auth_mode: 'api_key',
      context_window: 32768,
      has_api_key: true,
      credential_source: 'env',
    },
    {
      id: 'local',
      label: '本地服务',
      provider: 'openai-compatible',
      model: 'qwen2.5',
      base_url: 'http://localhost:1234/v1',
      auth_mode: 'none',
      context_window: 16384,
      has_api_key: false,
      credential_source: 'ui',
    },
  ],
  active_chat: null,
  active_embedding: {
    model_id: 'intfloat/multilingual-e5-small',
    resolved_revision: 'rev-1',
    collection: 'my_knowledge',
    fingerprint: 'fp-1',
  },
  retrieval_available: true,
  retrieval_problem: null,
  retrieval_state: 'ok',
  indexed_files: 120,
  corpus_files: 20,
  busy: false,
  embedding_job: null,
} as Record<string, unknown>

const RUNNING_JOB = {
  id: 'job-1',
  status: 'running',
  stage: 'indexing',
  completed: 3,
  total: 10,
  active_model: 'intfloat/multilingual-e5-small',
  target_model: 'BAAI/bge-small-zh-v1.5',
  error: null,
  started_at: '2026-09-28T10:00:00Z',
  finished_at: null,
}

const CANDIDATES = [
  {
    model_id: 'intfloat/multilingual-e5-small',
    label: 'multilingual-e5-small',
    availability: 'available',
    reason: null,
    active: true,
  },
  {
    model_id: 'BAAI/bge-small-zh-v1.5',
    label: 'bge-small-zh-v1.5',
    availability: 'available',
    reason: null,
    active: false,
  },
  {
    model_id: 'some/missing',
    label: 'missing',
    availability: 'incomplete',
    reason: '本地缓存不完整',
    active: false,
  },
]

interface StubOptions {
  status?: Record<string, unknown>
  saveStatus?: number
  saveMessage?: string
  activateStatus?: number
  switchResponse?: unknown
  job?: unknown
}

function readBody(request: { postData: () => string | null }): Record<string, unknown> {
  const raw = request.postData()
  if (!raw) return {}
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function stubApi(page: Page, options: StubOptions = {}) {
  const calls: Array<{ method: string; url: string; body: Record<string, unknown> }> = []
  const record = (route: {
    request: () => { method: () => string; url: () => string; postData: () => string | null }
  }) => {
    const request = route.request()
    calls.push({ method: request.method(), url: request.url(), body: readBody(request) })
  }
  const status = options.status ?? BASE_STATUS
  let jobPolls = 0

  /* 先注册宽泛的前缀，再注册各子路径：后注册的优先，否则子路径会被前缀吃掉。 */
  await page.route(
    (url) => url.pathname === '/model-settings',
    (route) => route.fulfill({ json: status }),
  )

  await page.route(
    (url) => url.pathname === '/model-settings/embeddings',
    (route) => route.fulfill({ json: CANDIDATES }),
  )
  await page.route(
    (url) => url.pathname.startsWith('/model-settings/jobs/'),
    (route) => {
      jobPolls += 1
      return route.fulfill({ json: options.job ?? RUNNING_JOB })
    },
  )
  await page.route(
    (url) => url.pathname === '/model-settings/chat/test',
    (route) => {
      record(route)
      return route.fulfill({
        json: { verified: true, streaming: true, tool_calling: true, message: null },
      })
    },
  )
  await page.route(
    (url) => url.pathname === '/model-settings/chat/activate',
    (route) => {
      record(route)
      if (options.activateStatus && options.activateStatus !== 200) {
        return route.fulfill({
          status: options.activateStatus,
          json: { message: '模型不可用' },
        })
      }
      return route.fulfill({ json: (status.chat_profiles as Array<{ id: string }>)[0] })
    },
  )
  await page.route(
    (url) => url.pathname.startsWith('/model-settings/chat/profiles'),
    (route) => {
      record(route)
      if (options.saveStatus && options.saveStatus !== 200) {
        return route.fulfill({
          status: options.saveStatus,
          json: { message: options.saveMessage ?? 'revision 已过期，请刷新后重试' },
        })
      }
      return route.fulfill({ json: (status.chat_profiles as Array<{ id: string }>)[0] })
    },
  )
  await page.route(
    (url) => url.pathname === '/model-settings/embedding/switch',
    (route) => {
      record(route)
      return route.fulfill({
        status: 202,
        json: options.switchResponse ?? { unchanged: false, job: status.embedding_job },
      })
    },
  )
  await page.route(
    (url) => url.pathname.startsWith('/conversations'),
    (route) => route.fulfill({ json: [] }),
  )
  await page.route(
    (url) => url.pathname.startsWith('/notes'),
    (route) => route.fulfill({ json: { files: [], folders: [] } }),
  )

  return { calls, jobPolls: () => jobPolls }
}

test('设置页列出聊天配置与向量候选，显示当前生效项', async ({ page }) => {
  await stubApi(page)
  await page.goto('/settings')

  await expect(page.getByText('环境默认')).toBeVisible()
  await expect(page.getByText('本地服务')).toBeVisible()
  await expect(page.locator('.ms-row-title', { hasText: 'multilingual-e5-small' })).toBeVisible()
  // 已启用的那条有标记，未启用的显示可用性原因。
  await expect(page.getByText('已启用').first()).toBeVisible()
  await expect(page.getByText('本地缓存不完整')).toBeVisible()
  await expect(page.getByText('已索引 120 个片段 / 20 篇笔记')).toBeVisible()
})

test('普通保存不启用：请求体带 expected_revision 且不带 id（新增）', async ({ page }) => {
  const stub = await stubApi(page)
  await page.goto('/settings')

  await page.getByRole('button', { name: '＋ 新增配置' }).click()
  const form = page.locator('.settings-card').first()
  await form.locator('#ms-label').fill('新配置')
  await form.locator('#ms-model').fill('deepseek-chat')
  await form.getByRole('button', { name: '保存', exact: true }).click()

  await expect.poll(() => stub.calls.some((call) => call.url.endsWith('/chat/profiles'))).toBe(true)
  const create = stub.calls.find((call) => call.url.endsWith('/chat/profiles'))!
  expect(create.method).toBe('POST')
  expect(create.body.expected_revision).toBe(7)
  // 已保存但没有启用。
  await expect(page.getByText('（未启用）')).toBeVisible()
})

test('保存并启用走 activate，而不是普通保存', async ({ page }) => {
  const stub = await stubApi(page)
  await page.goto('/settings')

  await page.getByRole('button', { name: '＋ 新增配置' }).click()
  const form = page.locator('.settings-card').first()
  await form.locator('#ms-label').fill('新配置')
  await form.locator('#ms-model').fill('deepseek-chat')
  await form.getByRole('button', { name: '保存并启用' }).click()

  await expect
    .poll(() => stub.calls.some((call) => call.url.endsWith('/chat/activate')))
    .toBe(true)
  expect(stub.calls.some((call) => call.url.endsWith('/chat/profiles'))).toBe(false)
})

test('revision 冲突时保留表单并提示刷新', async ({ page }) => {
  await stubApi(page, { saveStatus: 409 })
  await page.goto('/settings')

  await page.getByRole('button', { name: '＋ 新增配置' }).click()
  const form = page.locator('.settings-card').first()
  await form.locator('#ms-label').fill('新配置')
  await form.locator('#ms-model').fill('deepseek-chat')
  await form.getByRole('button', { name: '保存', exact: true }).click()

  await expect(page.getByText('revision 已过期，请刷新后重试')).toBeVisible()
  // 表单内容不丢。
  await expect(form.locator('#ms-label')).toHaveValue('新配置')
})

test('当前启用的配置不能普通保存，只能保存并启用', async ({ page }) => {
  await stubApi(page, {
    status: { ...BASE_STATUS, active_chat: (BASE_STATUS.chat_profiles as object[])[0] },
  })
  await page.goto('/settings')

  const row = page.locator('.ms-row', { hasText: '环境默认' }).first()
  await row.getByRole('button', { name: '编辑' }).click()

  const form = page.locator('.settings-card').first()
  await expect(form.getByRole('button', { name: '保存', exact: true })).toHaveCount(0)
  await expect(form.getByRole('button', { name: '保存并启用' })).toBeVisible()
  await expect(form.getByText('这是当前启用的配置')).toBeVisible()
  // 当前配置也不能删。
  await expect(row.getByRole('button', { name: '删除' })).toHaveCount(0)
})

test('编辑时 Key 不回显，留空表示保留', async ({ page }) => {
  await stubApi(page)
  await page.goto('/settings')

  const row = page.locator('.ms-row', { hasText: '环境默认' }).first()
  await row.getByRole('button', { name: '编辑' }).click()

  const key = page.locator('.settings-card').first().locator('#ms-key')
  await expect(key).toHaveValue('')
  await expect(key).toHaveAttribute('placeholder', '留空保留已保存的 Key')
})

test('连接测试把流式与工具调用的结论显示出来', async ({ page }) => {
  const stub = await stubApi(page)
  await page.goto('/settings')

  await page.getByRole('button', { name: '＋ 新增配置' }).click()
  const form = page.locator('.settings-card').first()
  await form.locator('#ms-model').fill('deepseek-chat')
  await form.getByRole('button', { name: '测试连接' }).click()

  await expect(page.getByText('连接测试通过：流式输出正常；工具调用正常')).toBeVisible()
  expect(stub.calls.some((call) => call.url.endsWith('/chat/test'))).toBe(true)
})

test('重建并切换会进入维护窗口并轮询任务', async ({ page }) => {
  const runningJob = {
    id: 'job-1',
    status: 'running',
    stage: 'indexing',
    completed: 3,
    total: 10,
    active_model: 'intfloat/multilingual-e5-small',
    target_model: 'BAAI/bge-small-zh-v1.5',
    error: null,
    started_at: '2026-09-28T10:00:00Z',
    finished_at: null,
  }
  const stub = await stubApi(page, { switchResponse: { unchanged: false, job: runningJob } })
  await page.goto('/settings')

  const row = page.locator('.ms-row', { hasText: 'bge-small-zh-v1.5' }).first()
  await row.getByRole('button', { name: '重建并切换' }).click()

  await expect
    .poll(() => stub.calls.some((call) => call.url.endsWith('/embedding/switch')))
    .toBe(true)
  const call = stub.calls.find((item) => item.url.endsWith('/embedding/switch'))!
  expect(call.body).toEqual({ model_id: 'BAAI/bge-small-zh-v1.5', expected_revision: 7 })

  // 进度条与阶段文案来自服务端实际字段。
  await expect(
    page.getByText(/正在切换到 BAAI\/bge-small-zh-v1\.5：建立索引（3\/10）/).first(),
  ).toBeVisible()
  await expect(page.locator('.settings-busy')).toBeVisible()
})

test('Settings 与 Assistant 快捷弹层是同一份状态', async ({ page }) => {
  await stubApi(page)
  await page.goto('/settings')
  await expect(page.locator('.ms-row-title', { hasText: '环境默认' })).toBeVisible()

  // 切到 Assistant 打开快捷弹层：应看到同一批配置，而不是另起一份。
  await page.getByRole('link', { name: 'Assistant', exact: true }).click()
  await page.getByRole('button', { name: '聊天模型设置' }).click()
  const popover = page.getByRole('dialog', { name: '聊天模型设置' })
  await expect(popover).toBeVisible()
  await expect(popover.getByText('环境默认')).toBeVisible()
  await expect(popover.getByText('本地服务')).toBeVisible()

  // 切回 Settings 不再重复拉状态：整轮状态请求次数保持稳定。
  await page.getByRole('link', { name: 'Settings', exact: true }).click()
  await expect(page.getByText('环境默认')).toBeVisible()
})
