import { expect, test, type Page } from '@playwright/test'

/**
 * A3：服务端消息身份与复制。接口固定响应拦截；用户消息带 editable=false
 * 与禁用原因，验证复制可用、编辑带原因禁用。
 */

const CONVERSATIONS = [
  { id: 'c-1', title: '你好', updated_at: '2026-09-28T10:00:00Z' },
]

const MESSAGES = [
  {
    id: 'u-1',
    role: 'user',
    content: '原始问题\n第二行原样保留**加粗**',
    created_at: '2026-09-28T10:00:01Z',
    turn_id: 't-1',
    citations: [],
    tool_steps: [],
    editable: false,
    edit_unavailable_reason: 'recovery_not_available',
  },
  {
    id: 'a-1',
    role: 'assistant',
    content: '回答正文',
    created_at: '2026-09-28T10:00:02Z',
    citations: [],
    tool_steps: [],
  },
]

const MODEL_SETTINGS = {
  revision: 7,
  chat_profiles: [],
  active_chat: {
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
}

async function stubApi(page: Page) {
  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    async (route) => {
      if (route.request().url().includes('/embeddings')) return route.fulfill({ json: [] })
      return route.fulfill({ json: MODEL_SETTINGS })
    },
  )
  await page.route(
    (url) => url.pathname === '/conversations' || url.pathname.startsWith('/conversations/'),
    async (route) => {
      const url = route.request().url()
      if (route.request().method() === 'GET' && /\/conversations$/.test(url)) {
        return route.fulfill({ json: CONVERSATIONS })
      }
      if (url.includes('/messages')) return route.fulfill({ json: MESSAGES })
      return route.fulfill({ json: { ...CONVERSATIONS[0], pending_draft: null } })
    },
  )
}

test.use({ permissions: ['clipboard-read', 'clipboard-write'] })

test('复制保留原始 Markdown 与换行', async ({ page }) => {
  await stubApi(page)
  await page.goto('/assistant')

  const userRow = page.locator('.msg-row.user').first()
  await expect(userRow).toContainText('原始问题')

  await userRow.getByRole('button', { name: '复制这条消息' }).click()
  await expect(userRow.getByText('已复制')).toBeVisible()

  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  // 原文的 Markdown 标记与换行都要保留（剪贴板可能带首尾空白，只断言内容）。
  expect(clipboard).toContain('原始问题')
  expect(clipboard).toContain('第二行原样保留**加粗**')
  expect(clipboard).toContain('\n')
})

test('编辑按钮带原因禁用', async ({ page }) => {
  await stubApi(page)
  await page.goto('/assistant')

  const edit = page.locator('.msg-row.user').first().getByRole('button', { name: '编辑这条消息' })
  await expect(edit).toBeDisabled()
  await expect(edit).toHaveAttribute('title', 'recovery_not_available')
})
