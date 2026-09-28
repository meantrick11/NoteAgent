import { expect, test, type Page } from '@playwright/test'

/**
 * Assistant 的用户行为回归。接口全部用固定响应拦截，不依赖后端是否启动，
 * 也不碰真实笔记；SSE 用可控的分片响应模拟。
 */

const CONVERSATIONS = [
  { id: 'c-1', title: '你好', updated_at: '2026-09-28T10:00:00Z' },
  { id: 'c-2', title: 'Agent 笔记', updated_at: '2026-09-28T09:00:00Z' },
]

const MESSAGES = [
  {
    id: 'm-1',
    role: 'user',
    content: 'Go 的并发模型是什么？',
    created_at: '2026-09-28T10:00:01Z',
    citations: [],
    tool_steps: [],
  },
  {
    id: 'm-2',
    role: 'assistant',
    content: 'Go 的并发模型基于 goroutine 和 channel [[cite:1]]。',
    created_at: '2026-09-28T10:00:02Z',
    citations: [
      { index: 1, file_name: 'Go.md', chunk_index: 0, quote: 'goroutine 是 Go 的并发单元' },
    ],
    tool_steps: [
      {
        name: 'search_relative_from_chromadb',
        status: 'ok',
        preview: '3 命中',
        arguments: '{"query":"go 并发"}',
      },
    ],
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

const NOTE = { file_name: 'Go.md', content: '前言\n\ngoroutine 是 Go 的并发单元，通道用于通信。\n\n后记' }

interface StubOptions {
  busy?: boolean
  chatEvents?: Array<[string, unknown]>
}

/** 读取请求体；GET 没有 body，postDataJSON() 会抛，所以自己兜住。 */
function readBody(request: { postData: () => string | null }): unknown {
  const raw = request.postData()
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

/** 拦截后端接口；返回记录到的请求，供断言用。
 *
 * 匹配用 URL 的 pathname 而不是 glob：glob 形式的 notes 通配会把 Vite 的
 * `/src/features/notes/api.ts` 模块请求也拦掉，页面会因为拿到 JSON 而直接加载不出来。
 */
async function stubApi(page: Page, options: StubOptions = {}) {
  const calls: Array<{ method: string; url: string; body: unknown }> = []
  const record = (route: { request: () => { method: () => string; url: () => string; postData: () => string | null } }) => {
    const request = route.request()
    calls.push({ method: request.method(), url: request.url(), body: readBody(request) })
  }

  // 先注册宽泛的 /chat，再注册更具体的两个；后注册的优先。
  await page.route(
    (url) => url.pathname.startsWith('/chat'),
    async (route) => {
      record(route)
      const events = options.chatEvents ?? [
        ['conversation', { id: 'c-1', title: '新会话' }],
        ['token', 'Go 用 '],
        ['token', 'goroutine'],
        ['answer', 'Go 用 goroutine 和 channel [[cite:1]] 表达并发。'],
      ]
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: events
          .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
          .join(''),
      })
    },
  )

  await page.route(
    (url) => url.pathname === '/chat/draft',
    async (route) => {
      record(route)
      return route.fulfill({
        json: {
          status: 'updated',
          pending_draft: {
            action: 'append',
            file_name: 'Go.md',
            content: '## 改过的正文\n',
            similar: [],
            existing_files: ['Go.md'],
          },
        },
      })
    },
  )

  await page.route(
    (url) => url.pathname === '/chat/review',
    async (route) => {
      record(route)
      return route.fulfill({ json: { status: 'written', action: 'append', file_name: 'Go.md' } })
    },
  )

  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    async (route) => {
      record(route)
      if (route.request().url().includes('/embeddings')) return route.fulfill({ json: [] })
      return route.fulfill({ json: { ...MODEL_SETTINGS, busy: options.busy === true } })
    },
  )

  await page.route(
    (url) => url.pathname === '/conversations' || url.pathname.startsWith('/conversations/'),
    async (route) => {
      record(route)
      const request = route.request()
      const url = request.url()
      if (request.method() === 'GET' && /\/conversations$/.test(url)) {
        return route.fulfill({ json: CONVERSATIONS })
      }
      if (url.includes('/messages')) return route.fulfill({ json: MESSAGES })
      return route.fulfill({ json: { ...CONVERSATIONS[0], pending_draft: null } })
    },
  )

  await page.route(
    (url) => url.pathname === '/notes' || url.pathname.startsWith('/notes/'),
    async (route) => {
      record(route)
      return route.fulfill({ json: NOTE })
    },
  )

  return calls
}

test('历史消息、引用与工具轨迹照旧显示', async ({ page }) => {
  await stubApi(page)
  await page.goto('/assistant')

  await expect(page.getByText('Go 的并发模型是什么？')).toBeVisible()
  // 历史里那条助手消息用的是另一套措辞，避免和实时回答的文案撞在一起。
  await expect(page.locator('.msg-row.assistant').first()).toContainText('并发模型基于')
  // 引用渲染成可点的角标。
  await expect(page.locator('.cite-ref')).toHaveCount(1)

  // 工具轨迹折叠在标题后面，点开才看到过程。
  const trace = page.locator('.msg-trace').first()
  await expect(trace.locator('.msg-trace-label')).toContainText('Explored')
  await expect(trace.locator('.msg-trace-list')).toBeHidden()
  await trace.locator('.msg-trace-head').click()
  await expect(trace.locator('.msg-trace-list')).toBeVisible()
  await expect(trace.locator('.msg-trace-list')).toContainText('Searched')
})

test('Enter 发送、Shift+Enter 换行，回答替换流式片段', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')

  const box = page.getByRole('textbox', { name: '输入你的问题' })
  await box.fill('Go 并发')
  await box.press('Shift+Enter')
  await expect(box).toHaveValue('Go 并发\n')
  await box.press('Enter')

  // 最终正文是 answer 那一份，不是 token 拼接的半成品。
  await expect(page.locator('.msg-row.assistant').last()).toContainText('表达并发')
  await expect(box).toHaveValue('')

  /* 首屏会自动打开最近一条会话，所以这一轮是发给它的。 */
  const chat = calls.find((call) => call.url.endsWith('/chat'))
  expect(chat?.body).toEqual({ question: 'Go 并发', conversation_id: 'c-1' })
})

test('新会话在首轮之后拿到正式 id', async ({ page }) => {
  await stubApi(page)
  await page.goto('/assistant')
  // 等历史消息先落位，否则"新对话"会和首次加载抢同一个视图。
  await expect(page.locator('.msg-row')).toHaveCount(2)
  await page.getByRole('button', { name: /新对话/ }).click()
  await expect(page.getByText('今天想学点什么？')).toBeVisible()
  await expect(page.locator('.msg-row')).toHaveCount(0)

  const box = page.getByRole('textbox', { name: '输入你的问题' })
  await box.fill('第一个问题')
  await box.press('Enter')
  await expect(page.locator('.msg-row.assistant')).toHaveCount(1)

  // 会话仍然可以继续发，说明 id 已经被采纳。
  await box.fill('第二个问题')
  await box.press('Enter')
  await expect(page.locator('.msg-row.user')).toHaveCount(2)
})

test('维护窗口里发送被拒，输入内容回到输入框', async ({ page }) => {
  const calls = await stubApi(page, { busy: true })
  await page.goto('/assistant')

  const box = page.getByRole('textbox', { name: '输入你的问题' })
  await box.fill('会被拒的问题')
  await box.press('Enter')

  // 聊天区里的说明与工具栏下方的常驻提示是两条不同的文案。
  await expect(
    page.locator('.msg-body', { hasText: '暂时不能发送消息；已有内容仍可查看' }),
  ).toBeVisible()
  // 输入框这时还没被清空，用户的问题原样留在原处。
  await expect(box).toHaveValue('会被拒的问题')
  expect(calls.some((call) => call.url.endsWith('/chat'))).toBe(false)
  await expect(page.locator('.model-toolbar-note')).toContainText('向量索引重建中')
})

test('点击引用打开笔记并选中片段；保存走正式笔记接口', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/assistant')

  await page.locator('.cite-ref').first().click()

  const pane = page.getByRole('complementary', { name: '引用与草稿面板' })
  await expect(pane).toBeVisible()
  await expect(pane.getByText('保存到 Markdown')).toBeVisible()

  const textarea = pane.getByRole('textbox', { name: '面板正文' })
  await expect(textarea).toHaveValue(NOTE.content)

  // 命中的片段被选中：选区非空，且起点就是 quote 的位置。
  const selection = await textarea.evaluate((el: HTMLTextAreaElement) => ({
    start: el.selectionStart,
    end: el.selectionEnd,
  }))
  expect(selection.end).toBeGreaterThan(selection.start)
  expect(NOTE.content.slice(selection.start, selection.end)).toBe('goroutine 是 Go 的并发单元')

  await pane.getByRole('button', { name: '保存到 Markdown' }).click()
  await expect(page.getByRole('status').filter({ hasText: '文件已保存' })).toBeVisible()
  const write = calls.find((call) => call.method === 'PUT' && call.url.includes('/notes/'))
  expect(write?.url).toContain('/notes/Go.md')
})

test('编辑引用后离开页面会先问一次，取消则留在原处', async ({ page }) => {
  await stubApi(page)
  await page.goto('/assistant')
  await page.locator('.cite-ref').first().click()

  const textarea = page.getByRole('textbox', { name: '面板正文' })
  await textarea.fill('我改过的正文')

  await page.getByRole('link', { name: 'Library', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '未保存修改' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '取消' }).click()

  // 取消离开：URL 与正文都保持原样。
  await expect(page).toHaveURL(/\/assistant$/)
  await expect(textarea).toHaveValue('我改过的正文')

  // 确认放弃才真的走。
  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await page.getByRole('dialog', { name: '未保存修改' }).getByRole('button', { name: '放弃修改' }).click()
  await expect(page).toHaveURL(/\/library$/)
})

test('会话菜单可以重命名与删除', async ({ page }) => {
  const calls = await stubApi(page)
  await page.route('**/conversations/c-2', async (route) => {
    const request = route.request()
    calls.push({ method: request.method(), url: request.url(), body: JSON.parse(request.postData() ?? '{}') })
    if (request.method() === 'PATCH') return route.fulfill({ json: { id: 'c-2', title: '改过的名字', updated_at: '' } })
    return route.fulfill({ status: 204, body: '' })
  })
  await page.goto('/assistant')

  const second = page.locator('.conversation-item').nth(1)
  await second.getByRole('button', { name: '更多' }).click()
  await page.getByRole('menuitem', { name: '重命名' }).click()
  const input = second.locator('.conversation-rename-input')
  await input.fill('改过的名字')
  await input.press('Enter')
  await expect(second.getByText('改过的名字')).toBeVisible()

  await second.getByRole('button', { name: '更多' }).click()
  await page.getByRole('menuitem', { name: '删除' }).click()
  const dialog = page.getByRole('dialog', { name: '删除对话' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '确认' }).click()
  await expect(page.locator('.conversation-item')).toHaveCount(1)
})
